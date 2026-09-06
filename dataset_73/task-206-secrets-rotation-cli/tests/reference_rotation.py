"""Reference model for secret rotation, following docs/rotation-spec.md literally.

Section numbers in comments refer to that document. This is the authority for
expected output; nothing is hardcoded.
"""
import json


class Rotator:
    def __init__(self, config):
        self.environments = list(config["environments"])
        self.grace_seconds = config["grace_seconds"]   # 8.0 starting policy

        self.now = 0
        self.consumers = {}          # consumer id -> environment
        self.acks = set()            # (consumer id, version)
        self.healthy = {env: True for env in self.environments}   # 2.4

        self.current = 1             # 3.1
        self.highest = 1
        self.live = {1}
        self.grace = None            # (version, started_at, window granted)

        self.in_flight = None        # version being rolled out
        self.stage_index = None
        self.completed = []          # environments already staged this rotation

        self.events = []
        self.errors = []

    # ------------------------------------------------------------- helpers
    def _at(self, record):
        """The replay clock is a high-water mark.

        A capture is merged from the runner's journal and the fleet's
        acknowledgement stream, so a record can carry a `t` behind the record
        before it. The runner's clock never runs backwards, and every event is
        stamped with the clock, not with the record's own `t`.
        """
        self.now = max(self.now, record["t"])

    def _event(self, kind, **fields):
        record = {"t": self.now, "kind": kind}
        record.update(fields)
        self.events.append(record)

    def _error(self, code, detail):
        self.errors.append({"code": code, "detail": str(detail)})

    def _consumers_in(self, env):
        """6.1 membership is read live, every time a stage is evaluated."""
        return [c for c, e in self.consumers.items() if e == env]

    # ------------------------------------------------------------- staging
    def _begin_stage(self, index):
        self.stage_index = index
        env = self.environments[index]
        self._event("stage", env=env, version=self.in_flight)   # 4.3, 6.2

    def _advance(self):
        """Evaluated after every record: complete, roll back, or wait."""
        while self.in_flight is not None:
            env = self.environments[self.stage_index]
            if not self.healthy[env]:                            # 7.1
                self._rollback(env)
                return
            waiting = [c for c in self._consumers_in(env)
                       if (c, self.in_flight) not in self.acks]  # 6.1, 5.2
            if waiting:
                return
            self._event("complete", env=env, version=self.in_flight)
            self.completed.append(env)
            if self.stage_index + 1 < len(self.environments):
                self._begin_stage(self.stage_index + 1)          # 6.2
                continue
            self._finish()
            return

    def _finish(self):
        version = self.in_flight
        self._event("rotated", version=version)                  # 6.3
        previous = self.current
        self.current = version
        self.live.add(version)
        if self.grace is not None:                               # 8.3
            stale, _started, _window = self.grace
            self.live.discard(stale)
            self._event("revoked", version=stale)
            self.grace = None
        # 8.0 the window is dated: the grant carries the policy in force now.
        self.grace = (previous, self.now, self.grace_seconds)
        self.in_flight = None
        self.stage_index = None
        self.completed = []

    def _rollback(self, staging_env):
        version = self.in_flight
        for env in reversed(self.completed):                     # 7.1
            self._event("rollback", env=env, version=version)
        self._event("rollback", env=staging_env, version=version)
        self.acks = {(c, v) for (c, v) in self.acks if v != version}   # 7.2
        self.in_flight = None
        self.stage_index = None
        self.completed = []

    def _sweep_grace(self):
        if self.grace is None:
            return
        version, started, window = self.grace
        if self.now - started >= window:                         # 8.1
            self.live.discard(version)
            self._event("revoked", version=version)              # 8.2
            self.grace = None

    # -------------------------------------------------------------- events
    def op_consumer(self, rec):
        self._at(rec)
        if rec["env"] not in self.healthy:                       # 2.3
            self._error("UNKNOWN_ENV", rec["env"])
            return
        self.consumers[rec["id"]] = rec["env"]                   # 2.2

    def op_health(self, rec):
        self._at(rec)
        if rec["env"] not in self.healthy:                       # 2.4
            self._error("UNKNOWN_ENV", rec["env"])
            return
        self.healthy[rec["env"]] = rec["ok"]

    def op_policy(self, rec):
        self._at(rec)
        # 8.0 the fleet's policy changes from here; grants already made keep
        # the window they were granted.
        self.grace_seconds = rec["grace_seconds"]

    def op_rotate(self, rec):
        self._at(rec)
        if rec.get("dry_run"):                                   # 4.1
            self._event("plan", version=self.highest + 1,
                        envs=list(self.environments))
            return
        if self.in_flight is not None:                           # 4.2
            self._error("ROTATION_IN_FLIGHT", self.in_flight)
            return
        self.highest += 1                                        # 3.2
        self.in_flight = self.highest
        self.completed = []
        self._begin_stage(0)

    def op_ack(self, rec):
        self._at(rec)
        if rec["consumer"] not in self.consumers:                # 5.1
            self._error("UNKNOWN_CONSUMER", rec["consumer"])
            return
        self.acks.add((rec["consumer"], rec["version"]))         # 5.2, 5.3

    def op_tick(self, rec):
        self._at(rec)

    def report(self):
        return {"events": self.events, "errors": self.errors,
                "state": {"current": self.current, "live": sorted(self.live)}}


HANDLERS = {"consumer": "op_consumer", "health": "op_health",
            "rotate": "op_rotate", "ack": "op_ack", "tick": "op_tick",
            "policy": "op_policy"}


def replay(records):
    rotator = Rotator(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        handler = HANDLERS.get(record["op"])
        if handler is None:
            raise ValueError("unknown op %r" % (record["op"],))
        getattr(rotator, handler)(record)
        rotator._advance()
        rotator._sweep_grace()
    return rotator.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("session must begin with a config record")
    return replay(records)
