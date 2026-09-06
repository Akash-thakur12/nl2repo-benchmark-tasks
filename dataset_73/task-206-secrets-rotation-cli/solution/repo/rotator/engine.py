"""The event loop that drives a rotation (spec sections 4-9)."""
import json

from .fleet import Fleet
from .rollout import Rollout
from .versions import Versions


class Engine:
    def __init__(self, config):
        self.fleet = Fleet(config["environments"])
        self.versions = Versions(config["grace_seconds"])
        self.now = 0
        self.acks = set()             # (consumer, version), remembered whenever
        self.rollout = None
        self.events = []
        self.errors = []

    # -------------------------------------------------------------- record
    def _at(self, record):
        """The replay clock is a high-water mark, never a raw copy of `t`.

        A capture is merged from the runner's journal and the fleet's
        acknowledgement stream, so a record may carry a `t` behind the record
        before it (see docs/session-format.md and archive/rot-4417.runner.log).
        The runner's clock does not run backwards, and every event is stamped
        with the clock rather than with the record's own `t`.
        """
        self.now = max(self.now, record["t"])

    def _event(self, kind, **fields):
        record = {"t": self.now, "kind": kind}
        record.update(fields)
        self.events.append(record)

    def _error(self, code, detail):
        self.errors.append({"code": code, "detail": str(detail)})

    # -------------------------------------------------------------- events
    def consumer(self, record):
        self._at(record)
        if not self.fleet.knows(record["env"]):
            self._error("UNKNOWN_ENV", record["env"])       # 2.3
            return
        self.fleet.register(record["id"], record["env"])

    def health(self, record):
        self._at(record)
        if not self.fleet.knows(record["env"]):
            self._error("UNKNOWN_ENV", record["env"])       # 2.4
            return
        self.fleet.set_health(record["env"], record["ok"])

    def policy(self, record):
        # 8.0 the fleet's retention policy changes from this moment on. A grace
        # period already counting down keeps the window it was granted.
        self._at(record)
        self.versions.set_policy(record["grace_seconds"])

    def rotate(self, record):
        self._at(record)
        if record.get("dry_run"):                           # 4.1 changes nothing
            self._event("plan", version=self.versions.next_number(),
                        envs=list(self.fleet.order))
            return
        if self.rollout is not None:                        # 4.2
            self._error("ROTATION_IN_FLIGHT", self.rollout.version)
            return
        self.rollout = Rollout(self.versions.take_next()).bind(self.fleet.order)
        self._event("stage", env=self.rollout.env,
                    version=self.rollout.version)           # 4.3

    def ack(self, record):
        self._at(record)
        if not self.fleet.has_consumer(record["consumer"]):
            self._error("UNKNOWN_CONSUMER", record["consumer"])   # 5.1
            return
        # 5.2, 5.3 remembered whatever the version and whatever the timing
        self.acks.add((record["consumer"], record["version"]))

    def tick(self, record):
        self._at(record)

    # ------------------------------------------------------------ progress
    def advance(self):
        """Evaluated after every record, and again after each completed stage."""
        while self.rollout is not None:
            env = self.rollout.env
            if not self.fleet.is_healthy(env):              # 7.1
                self._roll_back(env)
                return
            # 6.1 membership is re-read here, on every evaluation: consumers
            # register and move while a rollout is in flight.
            outstanding = [cid for cid in self.fleet.members_of(env)
                           if (cid, self.rollout.version) not in self.acks]
            if outstanding:                                 # 6.1
                return
            self._event("complete", env=env, version=self.rollout.version)
            if self.rollout.has_next():                     # 6.2
                self.rollout.advance()
                self._event("stage", env=self.rollout.env,
                            version=self.rollout.version)
                continue
            self._promote()
            return

    def _promote(self):
        version = self.rollout.version
        self._event("rotated", version=version)             # 6.3
        cut_short = self.versions.promote(version, self.now)
        if cut_short is not None:                           # 8.3
            self._event("revoked", version=cut_short)
        self.rollout = None

    def _roll_back(self, staging_env):
        version = self.rollout.version
        for env in self.rollout.reverse_completed():        # 7.1
            self._event("rollback", env=env, version=version)
        self._event("rollback", env=staging_env, version=version)
        self.acks = {(cid, v) for (cid, v) in self.acks if v != version}   # 7.2
        self.rollout = None                                 # 7.3 no grace period

    def sweep(self):
        due = self.versions.due_for_revocation(self.now)    # 8.1
        if due is not None:
            self.versions.revoke(due)
            self._event("revoked", version=due)             # 8.2

    def report(self):
        return {"events": self.events, "errors": self.errors,
                "state": self.versions.snapshot()}


DISPATCH = {"consumer": "consumer", "health": "health", "rotate": "rotate",
            "ack": "ack", "tick": "tick", "policy": "policy"}


def replay(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("a session must start with a config record")
    engine = Engine(records[0])
    for record in records[1:]:
        op = record["op"]
        if op == "end":
            break
        method = DISPATCH.get(op)
        if method is None:
            raise ValueError("unrecognised op {0!r}".format(op))
        getattr(engine, method)(record)
        engine.advance()
        engine.sweep()
    return engine.report()
