"""The key range and its chunks (spec sections 1, 2, 6).

The checkpoint lives in the job row and survives a restart. The range of the
chunk currently in flight does not: docs/runner-internals.md lists chunk_lo and
chunk_hi as process memory, materialised when the chunk is first attempted, so
a retune of chunk_size cannot reach a chunk that is already awaiting a retry
and a restart drops the range entirely.
"""


class Plan:
    def __init__(self, start, end, chunk_size, resume_from=None):
        self.start = start
        self.end = end
        self.chunk_size = chunk_size
        # 2.1, 2.2 a resume point below the range is raised to it; one at or
        # above the end leaves nothing to do
        origin = start if resume_from is None else resume_from
        self.checkpoint = max(origin, start)
        self.inflight = None

    @property
    def finished(self):
        return self.checkpoint >= self.end          # 1.4, 2.2

    def next_chunk(self):
        """1.2, 1.3, 2.4: the next chunk always starts at the checkpoint and
        never reaches past the end, so the last one may be short. Materialised
        once, at the first attempt; a retry replays the same range."""
        if self.inflight is None:
            first = self.checkpoint
            self.inflight = (first, min(first + self.chunk_size, self.end))
        return self.inflight

    def commit(self, upto):
        self.checkpoint = upto                      # 2.3 only on success
        self.inflight = None

    def adopt(self, cp):
        """A boot reports the job row as the monitoring sidecar read it off the
        reporting replica, which lags. Durable progress never moves backwards,
        so a report below what we already know is a stale read; one above it is
        real progress made by a process this capture did not record."""
        if cp is not None:
            self.checkpoint = max(self.checkpoint, cp)

    def forget_inflight(self):
        self.inflight = None                        # process memory, lost on boot

    def progress(self):
        total = max(self.end - self.start, 0)       # 6.2
        done = self.checkpoint - self.start         # 6.1
        percent = 100 if total == 0 else done * 100 // total   # 6.3
        return done, total, percent
