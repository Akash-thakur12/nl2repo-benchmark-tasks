from __future__ import annotations

import time

from engine.bucket import TokenBucket

_NEG_INF = float("-inf")
_DEFAULT_TENANT = "*"


class Policy:
    """One control-plane row: what a tenant's limit is from ``effective_at`` on."""

    __slots__ = ("tenant", "capacity", "rate", "effective_at", "revision", "note")

    def __init__(self, tenant, capacity, rate, effective_at, revision, note=""):
        self.tenant = tenant
        self.capacity = float(capacity)
        self.rate = float(rate)
        self.effective_at = float(effective_at)
        self.revision = int(revision)
        self.note = note

    def __repr__(self):                                   # pragma: no cover
        return ("Policy(tenant=%r, capacity=%r, rate=%r, effective_at=%r, "
                "revision=%r)" % (self.tenant, self.capacity, self.rate,
                                  self.effective_at, self.revision))


class PolicyTable:
    """The control-plane export, indexed so any instant can be resolved.

    Rows arrive in whatever order the exporter emitted them (in practice sorted
    by ``revision``), so they are re-keyed by tenant and sorted here.
    """

    def __init__(self, rows, default_capacity, default_rate):
        self._by_tenant = {}
        # The engine's own ``capacity``/``rate`` are the baseline default: a row
        # that has been in force since before any timestamp can be observed.
        self._append(Policy(_DEFAULT_TENANT, default_capacity, default_rate,
                            _NEG_INF, -1, "engine default"))
        for row in rows or ():
            self._append(Policy(
                row.get("tenant", _DEFAULT_TENANT),
                row["capacity"],
                row["rate"],
                row.get("effective_at", _NEG_INF),
                row.get("revision", 0),
                row.get("note", ""),
            ))
        for bucket in self._by_tenant.values():
            bucket.sort(key=lambda p: (p.effective_at, p.revision))
        self._edges = sorted({p.effective_at
                              for rows_ in self._by_tenant.values()
                              for p in rows_
                              if p.effective_at != _NEG_INF})

    def _append(self, policy):
        self._by_tenant.setdefault(policy.tenant, []).append(policy)

    @staticmethod
    def tenant_of(key):
        """The tenant a key belongs to, or ``None`` when the key names none."""
        text = str(key)
        head, sep, _rest = text.partition(":")
        return head if sep else None

    @staticmethod
    def _in_force(rows, when):
        found = None
        for policy in rows:
            if policy.effective_at <= when:
                found = policy
            else:
                break
        return found

    def resolve(self, key, when):
        """The row governing ``key`` at instant ``when``."""
        tenant = self.tenant_of(key)
        if tenant is not None:
            rows = self._by_tenant.get(tenant)
            if rows:
                found = self._in_force(rows, when)
                if found is not None:
                    return found
        return self._in_force(self._by_tenant[_DEFAULT_TENANT], when)

    def edges_between(self, start, end):
        """Change instants in ``(start, end]``, ascending."""
        return [edge for edge in self._edges if start < edge <= end]


class KeyTimeline:
    """``PolicyTable`` seen through one key: what a ``TokenBucket`` needs."""

    def __init__(self, table, key):
        self._table = table
        self._key = key

    def at(self, when):
        policy = self._table.resolve(self._key, when)
        return policy.capacity, policy.rate

    def edges(self, start, end):
        return self._table.edges_between(start, end)


class RateLimiterEngine:
    """Per-key token bucket plus an independent per-key sliding-window limiter.

    Time comes from ``config["clock"]`` (a zero-argument callable returning
    seconds), which defaults to ``time.time`` but can be replaced with a fake
    clock for deterministic tests.  The clock is wall time on the gateway host
    and is not assumed to be monotonic.
    """

    def __init__(self, config=None):
        cfg = config or {}
        self._capacity = cfg.get("capacity", 10)
        self._rate = cfg.get("rate", 1.0)
        self._clock = cfg.get("clock", time.time)
        self._policies = cfg.get("policies")
        self._build_table()
        self._buckets = {}
        self._windows = {}

    def _build_table(self):
        self._table = PolicyTable(self._policies, self._capacity, self._rate)

    def reset(self):
        self._buckets = {}
        self._windows = {}

    def configure(self, options):
        self._capacity = options.get("capacity", self._capacity)
        self._rate = options.get("rate", self._rate)
        self._clock = options.get("clock", self._clock)
        if "policies" in options:
            self._policies = options["policies"]
        self._build_table()
        self.reset()

    def policy_for(self, key, at=None):
        """The control-plane row governing ``key`` at ``at`` (default: now)."""
        when = self._clock() if at is None else at
        return self._table.resolve(key, when)

    def _bucket(self, key):
        bucket = self._buckets.get(key)
        if bucket is None:
            now = self._clock()
            timeline = KeyTimeline(self._table, key)
            capacity, rate = timeline.at(now)
            bucket = TokenBucket(capacity, rate, now, timeline=timeline)
            self._buckets[key] = bucket
        return bucket

    def allow(self, key, cost=1):
        return self._bucket(key).take(cost, self._clock())

    def tokens(self, key):
        return self._bucket(key).level(self._clock())

    def sliding_window(self, key, window_sec, max_reqs):
        now = self._clock()
        timeline = self._windows.get(key)
        if timeline is None:
            timeline = []
            self._windows[key] = timeline

        cutoff = now - window_sec
        # The timeline is a log of observed arrival times.  A clock correction
        # can put an older arrival after a newer one, so expiry is decided for
        # every entry rather than by peeling a prefix off the front.
        kept = [stamp for stamp in timeline if stamp > cutoff]
        self._windows[key] = kept
        if len(kept) < max_reqs:
            kept.append(now)
            return True
        return False
