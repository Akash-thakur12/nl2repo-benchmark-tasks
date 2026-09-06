"""The supervisor itself: records in, report out (spec sections 1, 2, 5, 6)."""
import json

from .worker import DRAINING, RUNNING, STOPPED, Worker


class Policy:
    """The knobs the config record sets."""

    def __init__(self, config):
        self.backoff = list(config["backoff_ms"])
        self.reset_after = config["reset_after_ms"]
        self.timeout = config["heartbeat_timeout_ms"]
        self.max_restarts = config["max_restarts"]
        self.window = config["restart_window_ms"]

    def backoff_for(self, attempt):
        # 3.4 the last entry repeats once the table runs out
        if attempt >= len(self.backoff):
            return self.backoff[-1]
        return self.backoff[attempt]


class Fleet:
    def __init__(self, config):
        self.policy = Policy(config)
        self.names = list(config["workers"])              # 2.2 visiting order
        self.workers = {name: Worker(name) for name in self.names}
        self.clock = 0
        self.events = []
        self.errors = []

    # -------------------------------------------------------------- helpers
    def _record_events(self, worker, kinds):
        for kind in kinds:
            self.events.append({"t": self.clock, "worker": worker.name,
                                "kind": kind})

    def _find(self, name):
        worker = self.workers.get(name)
        if worker is None:                                # 1.3
            self.errors.append({"code": "UNKNOWN_WORKER", "detail": name})
        return worker

    def _crash(self, worker):
        self._record_events(worker, worker.go_down(self.clock, self.policy))

    # -------------------------------------------------------------- records
    def apply(self, record):
        self.clock = record["t"]
        handler = getattr(self, "_on_" + record["op"], None)
        if handler is None:
            raise ValueError("unknown op %r" % (record["op"],))
        handler(record)
        self._sweep()

    def _on_tick(self, record):
        pass                                              # 1.1 time only

    def _on_heartbeat(self, record):
        worker = self._find(record["worker"])
        if worker is not None and worker.live:            # 2.4
            worker.note_beat(self.clock)

    def _on_crash(self, record):
        worker = self._find(record["worker"])
        if worker is not None and worker.live:
            self._crash(worker)

    def _on_work(self, record):
        worker = self._find(record["worker"])
        if worker is not None and worker.live:            # 4.1
            worker.take_work()

    def _on_finished(self, record):
        worker = self._find(record["worker"])
        if worker is None or not worker.live:             # 4.2
            return
        worker.drop_work()
        if worker.state == DRAINING:                      # 5.2
            worker.state = STOPPED
            self._record_events(worker, ["drained"])

    def _on_drain(self, record):
        worker = self._find(record["worker"])
        if worker is None or worker.state != RUNNING:     # 5.5
            return
        if worker.holding_work:
            worker.state = DRAINING                       # 5.2
            return
        worker.state = STOPPED                            # 5.1
        self._record_events(worker, ["drained"])

    # ------------------------------------------------------------- sweeping
    def _sweep(self):
        for name in self.names:                           # 3.5 restarts first
            worker = self.workers[name]
            if worker.restart_ready(self.clock):
                worker.bring_up(self.clock)
                self._record_events(worker, ["restarted"])

        for name in self.names:                           # 2.2 then health
            worker = self.workers[name]
            if not worker.live:                           # 5.4
                continue
            if worker.rested(self.clock, self.policy.reset_after):
                worker.forgive()                          # 3.6
            if worker.unhealthy_at(self.clock, self.policy.timeout):
                self._crash(worker)                       # 2.3

    def report(self):
        return {"events": self.events,                    # 6.1
                "workers": [self.workers[name].snapshot()
                            for name in self.names],      # 6.2
                "errors": self.errors}                    # 6.3


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("session must begin with a config record")
    fleet = Fleet(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        fleet.apply(record)
    return fleet.report()
