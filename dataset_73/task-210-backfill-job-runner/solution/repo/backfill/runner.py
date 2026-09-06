"""The runner itself (spec sections 4, 5, 7).

A capture is stitched from every process that has worked the job, so the file
carries several segments. Each `boot` record opens one, gives the wall-second
at which that process's clock reads zero, and reports the job row as the
sidecar read it. Only the absolute timeline `at + t` means anything across the
file. What a boot keeps and what it drops is settled by the durability table in
docs/runner-internals.md.
"""
import json

from .plan import Plan
from .window import SlidingWindow

OK = "ok"
FAIL = "fail"


class Runner:
    def __init__(self, config):
        self.plan = Plan(config["start"], config["end"], config["chunk_size"],
                         config.get("resume_from"))
        self.limit = SlidingWindow(config["max_chunks_per_window"],
                                   config["window_seconds"])
        self.max_attempts = config["max_attempts"]
        self.outcomes = list(config.get("outcomes") or [])

        self.now = 0
        self.at = 0
        self.paused = False
        self.halted = False
        self.failures = 0
        self.consumed = 0
        self.attempts = []
        self.waits = 0

    def _stamp(self, record):
        self.now = self.at + record["t"]
        return self.now

    def _next_outcome(self):
        # 4.1 anything past the end of the list succeeds
        result = self.outcomes[self.consumed] if self.consumed < len(self.outcomes) else OK
        self.consumed += 1
        return result

    def attempt(self, record):
        self._stamp(record)
        if self.halted or self.paused or self.plan.finished:   # 4.4, 5.1
            return
        if not self.limit.allows(self.now):                    # 3.3 wait, never skip
            self.waits += 1
            return

        first, last = self.plan.next_chunk()
        self.limit.record(self.now)
        outcome = self._next_outcome()
        self.attempts.append({"t": self.now, "from": first, "to": last,
                              "outcome": outcome})

        if outcome == OK:
            self.plan.commit(last)                             # 4.2
            self.failures = 0                                  # 4.5
            return
        self.failures += 1                                     # 4.3
        if self.failures >= self.max_attempts:                 # 4.4
            self.halted = True

    def pause(self, record):
        self._stamp(record)
        self.paused = True                                     # 5.1, 5.2

    def resume(self, record):
        self._stamp(record)
        self.paused = False                                    # 5.3 halt is final

    def tick(self, record):
        self._stamp(record)                                    # 3.4

    def boot(self, record):
        # A new process takes over. Its clock reads zero at wall-second `at`.
        self.at = record.get("at", 0)
        self._stamp(record)
        self.plan.adopt(record.get("cp"))       # job row, never backwards
        self.failures = 0                       # process memory, gone
        self.plan.forget_inflight()             # process memory, gone
        # the limiter belongs to the API gateway: a restart is not a reset,
        # and halted/paused live in the job row, so they ride through untouched

    def policy(self, record):
        # an operator retuned the control table; it applies from here on and
        # cannot reach a chunk that is already in flight
        self._stamp(record)
        if "chunk_size" in record:
            self.plan.chunk_size = record["chunk_size"]
        self.limit.retune(record.get("max_chunks_per_window"),
                          record.get("window_seconds"))

    def report(self):
        done, total, percent = self.plan.progress()
        return {
            "attempts": self.attempts,
            "state": {"checkpoint": self.plan.checkpoint, "done": done,
                      "total": total, "percent": percent,
                      "halted": self.halted, "paused": self.paused},
            "waits": self.waits,
        }


DISPATCH = {"attempt": "attempt", "pause": "pause", "resume": "resume",
            "tick": "tick", "boot": "boot", "policy": "policy"}


def replay(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("a session must start with a config record")
    runner = Runner(records[0])
    for record in records[1:]:
        op = record["op"]
        if op == "end":
            break
        method = DISPATCH.get(op)
        if method is None:
            raise ValueError("unrecognised op {0!r}".format(op))
        getattr(runner, method)(record)
    return runner.report()
