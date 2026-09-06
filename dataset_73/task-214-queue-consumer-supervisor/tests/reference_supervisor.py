"""Reference model for the worker supervisor, following docs/supervisor-spec.md
literally. Section numbers in comments refer to that document. This is the
authority for expected output; nothing is hardcoded.
"""
import json

RUNNING = "running"
DOWN = "down"
DRAINING = "draining"
STOPPED = "stopped"
FAILED = "failed"


class Worker:
    def __init__(self, name):
        self.name = name
        self.state = RUNNING                 # 1.2
        self.last_heartbeat = 0
        self.started_at = 0
        self.busy = False
        self.consecutive = 0                 # 3.4 index into the backoff table
        self.history = []                    # 3.2 crash times
        self.due = None                      # 3.4 when a restart is due
        self.restarts = 0
        self.crashes = 0


class Supervisor:
    def __init__(self, config):
        self.order = list(config["workers"])
        self.backoff = config["backoff_ms"]
        self.reset_after = config["reset_after_ms"]
        self.timeout = config["heartbeat_timeout_ms"]
        self.max_restarts = config["max_restarts"]
        self.window = config["restart_window_ms"]

        self.workers = {name: Worker(name) for name in self.order}
        self.now = 0
        self.events = []
        self.errors = []

    # ------------------------------------------------------------- helpers
    def _event(self, worker, kind):
        self.events.append({"t": self.now, "worker": worker.name, "kind": kind})

    def _lookup(self, name):
        worker = self.workers.get(name)
        if worker is None:                                   # 1.3
            self.errors.append({"code": "UNKNOWN_WORKER", "detail": name})
        return worker

    def _backoff_for(self, attempt):
        # 3.4 past the end of the table the last entry repeats
        return self.backoff[min(attempt, len(self.backoff) - 1)]

    def _stop(self, worker):
        """3.1-3.4: a crash, however it was caused."""
        worker.state = DOWN
        worker.busy = False                                  # 4.3
        worker.crashes += 1
        self._event(worker, "crashed")
        worker.history.append(self.now)                      # 3.2
        recent = [t for t in worker.history if self.now - t <= self.window]
        worker.history = recent
        if len(recent) > self.max_restarts:                  # 3.3
            worker.state = FAILED
            worker.due = None
            self._event(worker, "failed")
            return
        worker.due = self.now + self._backoff_for(worker.consecutive)

    # -------------------------------------------------------------- events
    def op_heartbeat(self, record):
        self.now = record["t"]
        worker = self._lookup(record["worker"])
        if worker is None or worker.state not in (RUNNING, DRAINING):
            return                                           # 2.4
        worker.last_heartbeat = self.now

    def op_crash(self, record):
        self.now = record["t"]
        worker = self._lookup(record["worker"])
        if worker is None or worker.state not in (RUNNING, DRAINING):
            return
        self._stop(worker)

    def op_work(self, record):
        self.now = record["t"]
        worker = self._lookup(record["worker"])
        if worker is None or worker.state not in (RUNNING, DRAINING):
            return
        worker.busy = True                                   # 4.1

    def op_finished(self, record):
        self.now = record["t"]
        worker = self._lookup(record["worker"])
        if worker is None or worker.state not in (RUNNING, DRAINING):
            return                                           # 4.2
        worker.busy = False
        if worker.state == DRAINING:                         # 5.2
            worker.state = STOPPED
            self._event(worker, "drained")

    def op_drain(self, record):
        self.now = record["t"]
        worker = self._lookup(record["worker"])
        if worker is None or worker.state != RUNNING:
            return                                           # 5.5
        if worker.busy:
            worker.state = DRAINING                          # 5.2
            return
        worker.state = STOPPED                               # 5.1
        self._event(worker, "drained")

    def op_tick(self, record):
        self.now = record["t"]

    # ------------------------------------------------------------ sweeping
    def sweep(self):
        for name in self.order:                              # 2.2 configuration order
            worker = self.workers[name]
            if worker.state == DOWN and worker.due is not None \
                    and worker.due <= self.now:              # 3.5 restarts first
                worker.state = RUNNING
                worker.last_heartbeat = self.now
                worker.started_at = self.now
                worker.consecutive += 1
                worker.restarts += 1
                worker.due = None
                self._event(worker, "restarted")

        for name in self.order:
            worker = self.workers[name]
            if worker.state not in (RUNNING, DRAINING):
                continue
            if self.now - worker.started_at >= self.reset_after:   # 3.6
                worker.consecutive = 0
            if self.now - worker.last_heartbeat > self.timeout:    # 2.1, 2.3
                self._stop(worker)

    def report(self):
        return {
            "events": self.events,
            "workers": [{"name": name,
                         "state": self.workers[name].state,
                         "restarts": self.workers[name].restarts,
                         "crashes": self.workers[name].crashes}
                        for name in self.order],
            "errors": self.errors,
        }


HANDLERS = {"heartbeat": "op_heartbeat", "crash": "op_crash", "work": "op_work",
            "finished": "op_finished", "drain": "op_drain", "tick": "op_tick"}


def replay(records):
    supervisor = Supervisor(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        handler = HANDLERS.get(record["op"])
        if handler is None:
            raise ValueError("unknown op %r" % (record["op"],))
        getattr(supervisor, handler)(record)
        supervisor.sweep()
    return supervisor.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("session must begin with a config record")
    return replay(records)
