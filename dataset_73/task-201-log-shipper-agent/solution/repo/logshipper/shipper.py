"""The shipper state machine (environment/docs/shipper-spec.md).

Section numbers in comments refer to that document, except where a comment
names collector-api.md or the clock-step incident note.
"""
from .buffer import PendingBuffer, PendingLine
from .config import Config
from .files import FileSet

RETRYABLE = frozenset((500, 502, 503))
PERMANENT = frozenset((400, 413, 422))


class InFlightBatch:
    """collector-api.md section 3: the retry budget is negotiated per request
    at submission and travels with the request. Reconfiguring the shipper does
    not change the budget of a batch that is already in flight."""

    __slots__ = ("lines", "budget")

    def __init__(self, lines, budget):
        self.lines = lines
        self.budget = budget


class Shipper:
    def __init__(self, config_record):
        self.cfg = Config(config_record)
        self.files = FileSet()
        self.buffer = PendingBuffer(self.cfg.spool_max_bytes)
        self.inflight = {}
        self.clock = 0
        self.next_id = 1
        self.delivered = []
        self.dead_letters = []

    # ---------------------------------------------------------------- clock
    def _advance(self, record):
        """Section 1: `t` is the host's wall clock as the shipper recorded it,
        and a disciplined host can step it backwards. The replay clock never
        decreases (incident-2026-02-11-clock-step.md, Resolution)."""
        if "t" in record:
            self.clock = max(self.clock, record["t"])

    # ------------------------------------------------------------- flushing
    def _flush_due(self):
        if not len(self.buffer):
            return False
        if len(self.buffer) >= self.cfg.max_lines:                     # 4.1
            return True
        if self.buffer.size >= self.cfg.max_bytes:                     # 4.2
            return True
        return self.clock - self.buffer.oldest_read_at() >= self.cfg.max_age_ms   # 4.3

    def flush(self):
        # 4.4: take the largest prefix the collector accepts as one request,
        # repeated while a trigger still holds.
        while self._flush_due():
            batch = self.buffer.take_batch(self.cfg.max_lines, self.cfg.max_bytes)
            for line in batch:
                line.attempts += 1
            self.inflight[self.next_id] = InFlightBatch(batch, self.cfg.max_retries)
            self.next_id += 1                                          # 4.5, 4.6

    def enforce_spool_limit(self):
        self.buffer.enforce_limit()                                    # 6.1-6.3

    # --------------------------------------------------------------- events
    def config(self, record):
        # 9: the shipper reloads on SIGHUP, so a capture may carry further
        # config records after the first.
        self._advance(record)
        self.cfg.apply(record)
        self.buffer.set_limit(self.cfg.spool_max_bytes)                # 6.3

    def append(self, record):
        self._advance(record)
        handle = self.files.get_or_create(record["file"])
        handle.append(record["data"].encode("utf-8"))
        # 2.2: a consumed line is stamped with the clock as it stands.
        fresh = [PendingLine(text, record["file"], handle.generation, offset, self.clock)
                 for text, offset in handle.take_complete_lines()]        # 2.1-2.3
        self.buffer.extend(fresh)

    def rotate(self, record):
        self._advance(record)
        self.files.get_or_create(record["file"]).rotate()               # 3.1-3.3

    def tick(self, record):
        self._advance(record)

    def restart(self, record):
        self._advance(record)
        self.buffer.clear()                                             # 7.1
        self.inflight = {}
        for handle in self.files.values():
            handle.rewind_to_acked()                                    # 7.2

    def response(self, record):
        self._advance(record)
        batch = self.inflight.pop(record["batch"], None)
        if batch is None:                                               # 5.5, 7.3
            return
        status = record["status"]
        if status == 200:
            self._accept(record["batch"], batch.lines)                  # 5.1
        elif status in RETRYABLE:
            self._retry(batch)                                          # 5.2, 5.3
        elif status in PERMANENT:
            self.dead_letters.extend(line.text for line in batch.lines)  # 5.4
        else:
            raise ValueError("unrecognised status %r" % (status,))

    def _accept(self, batch_id, lines):
        self.delivered.append({"id": batch_id, "lines": [ln.text for ln in lines]})
        for line in lines:
            self.files.get_or_create(line.file).ack(line.generation, line.offset)

    def _retry(self, batch):
        survivors = []
        for line in batch.lines:
            line.attempts += 1
            if line.attempts > batch.budget:                            # 5.3
                self.dead_letters.append(line.text)
            else:
                survivors.append(line)
        self.buffer.push_front(survivors)                               # 5.2, 6.3
