"""Reference model for the backfill runner, following docs/backfill-spec.md,
docs/session-format.md and docs/runner-internals.md literally. Section numbers
in comments refer to those documents. This is the authority for expected
output; nothing is hardcoded.
"""
import json

# Fields a `policy` record may retune (session-format.md, "policy").
POLICY_FIELDS = ("chunk_size", "max_chunks_per_window", "window_seconds")


class Runner:
    def __init__(self, config):
        self.start = config["start"]
        self.end = config["end"]
        self.chunk_size = config["chunk_size"]
        self.max_attempts = config["max_attempts"]
        self.max_per_window = config["max_chunks_per_window"]
        self.window = config["window_seconds"]
        self.outcomes = list(config.get("outcomes") or [])

        checkpoint = config.get("resume_from", self.start)
        self.checkpoint = max(checkpoint, self.start)        # 2.1, 2.2

        # runner-internals.md durability table -----------------------------
        # job row      : checkpoint, halted, paused        (survive a boot)
        # process mem  : failures, the in-flight range     (lost on a boot)
        # external     : the gateway's sliding window      (a boot cannot
        #                                                   touch it)
        self.now = 0
        self.at = 0                                          # segment origin
        self.paused = False
        self.halted = False
        self.failures = 0
        self.inflight = None                                 # materialised range
        self.taken = 0                                       # attempts consumed
        self.recent = []                                     # attempt times (absolute)
        self.attempts = []
        self.waits = 0

    # ------------------------------------------------------------- helpers
    @property
    def finished(self):
        return self.checkpoint >= self.end                   # 1.4, 2.2

    def _stamp(self, record):
        """A capture is stitched from one or more runner processes and each
        stamps `t` as seconds since its own start, so the only timeline that
        means anything across the file is `at + t`."""
        self.now = self.at + record["t"]
        return self.now

    def _next_chunk(self):
        """The in-flight range is materialised once, when the chunk is first
        attempted, and lives in process memory until it commits or the process
        dies. A retune of chunk_size cannot reach a chunk already in flight."""
        if self.inflight is None:
            first = self.checkpoint                          # 2.4
            last = min(first + self.chunk_size, self.end)    # 1.2, 1.3
            self.inflight = (first, last)
        return self.inflight

    def _rate_allows(self):
        # 3.1 sliding window: an earlier attempt is still inside when the gap is
        # strictly less than the window
        live = [t for t in self.recent if self.now - t < self.window]
        self.recent = live
        return len(live) < self.max_per_window

    def _outcome(self):
        if self.taken < len(self.outcomes):                  # 4.1
            result = self.outcomes[self.taken]
        else:
            result = "ok"
        self.taken += 1
        return result

    # -------------------------------------------------------------- events
    def op_attempt(self, record):
        self._stamp(record)
        if self.halted or self.paused or self.finished:      # 4.4, 5.1
            return
        if not self._rate_allows():                          # 3.3
            self.waits += 1
            return

        first, last = self._next_chunk()
        self.recent.append(self.now)                         # 3.2 retries count
        outcome = self._outcome()
        self.attempts.append({"t": self.now, "from": first, "to": last,
                              "outcome": outcome})
        if outcome == "ok":
            self.checkpoint = last                           # 4.2, 2.3
            self.inflight = None                             # committed
            self.failures = 0                                # 4.5
            return
        self.failures += 1                                   # 4.3 (in-flight kept)
        if self.failures >= self.max_attempts:               # 4.4
            self.halted = True

    def op_pause(self, record):
        self._stamp(record)
        self.paused = True                                   # 5.1, 5.2

    def op_resume(self, record):
        self._stamp(record)
        self.paused = False                                  # 5.3 halted stays halted

    def op_tick(self, record):
        self._stamp(record)                                  # 3.4

    def op_boot(self, record):
        """A new runner process takes over. Its clock reads zero at wall-second
        `at`. Everything the job row holds survives; everything process memory
        held does not; the gateway's limiter is nobody's to reset."""
        self.at = record.get("at", 0)
        self._stamp(record)
        cp = record.get("cp")
        if cp is not None:
            # `cp` is the sidecar's read of the job row off the reporting
            # replica, so it may lag a commit the dead process already made.
            # Durable progress never goes backwards.
            self.checkpoint = max(self.checkpoint, cp)
        self.failures = 0                                    # process memory
        self.inflight = None                                 # process memory

    def op_policy(self, record):
        """An operator retuned the control table. It applies from here on and
        cannot reach a chunk already in flight."""
        self._stamp(record)
        for field in POLICY_FIELDS:
            if field in record:
                setattr(self, {"chunk_size": "chunk_size",
                               "max_chunks_per_window": "max_per_window",
                               "window_seconds": "window"}[field],
                        record[field])

    def report(self):
        total = max(self.end - self.start, 0)                # 6.2
        done = self.checkpoint - self.start                  # 6.1
        percent = 100 if total == 0 else done * 100 // total  # 6.3
        return {
            "attempts": self.attempts,
            "state": {"checkpoint": self.checkpoint, "done": done,
                      "total": total, "percent": percent,
                      "halted": self.halted, "paused": self.paused},
            "waits": self.waits,
        }


HANDLERS = {"attempt": "op_attempt", "pause": "op_pause",
            "resume": "op_resume", "tick": "op_tick",
            "boot": "op_boot", "policy": "op_policy"}


def replay(records):
    runner = Runner(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        handler = HANDLERS.get(record["op"])
        if handler is None:
            raise ValueError("unknown op %r" % (record["op"],))
        getattr(runner, handler)(record)
    return runner.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("session must begin with a config record")
    return replay(records)
