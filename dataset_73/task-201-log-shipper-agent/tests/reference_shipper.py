"""Reference model for the log shipper, following environment/docs/shipper-spec.md,
environment/docs/collector-api.md and environment/docs/session-format.md
literally. This is the authority for expected output; nothing is hardcoded.

Kept deliberately plain and section-numbered so a reviewer can check it against
the specification line by line.
"""
import json


class Line:
    __slots__ = ("text", "nbytes", "file", "gen", "offset", "t", "attempts")

    def __init__(self, text, file, gen, offset, t):
        self.text = text
        self.nbytes = len(text.encode("utf-8")) + 1   # 4.2: + the stripped newline
        self.file = file
        self.gen = gen
        self.offset = offset
        self.t = t
        self.attempts = 0


class Batch:
    """An in-flight request. collector-api.md section 3: the retry budget is
    negotiated per request at submission and travels with the request, so a
    later reload does not change the budget of a batch already in flight."""
    __slots__ = ("lines", "budget")

    def __init__(self, lines, budget):
        self.lines = lines
        self.budget = budget


class FileState:
    __slots__ = ("stream", "read_offset", "acked_offset", "gen")

    def __init__(self):
        self.stream = bytearray()
        self.read_offset = 0
        self.acked_offset = 0
        self.gen = 0


RETRY_STATUSES = {500, 502, 503}
PERMANENT_STATUSES = {400, 413, 422}
CONFIG_FIELDS = ("max_lines", "max_bytes", "max_age_ms", "max_retries", "spool_max_bytes")


class Shipper:
    def __init__(self, config):
        self.files = {}
        self.pending = []
        self.inflight = {}
        self.next_batch_id = 1
        self.now = 0

        self.delivered = []
        self.dlq = []
        self.dropped = 0

        self._load_config(config)

    # ------------------------------------------------------------- helpers
    def _load_config(self, config):
        # 9: every config record carries all five limits; a reload replaces them.
        for name in CONFIG_FIELDS:
            setattr(self, name, config[name])

    def _advance(self, rec):
        # 1: `t` is host wall clock and may step backwards. The replay clock
        # never decreases (incident-2026-02-11-clock-step.md, Resolution).
        if "t" in rec:
            self.now = max(self.now, rec["t"])

    def _file(self, name):
        if name not in self.files:
            self.files[name] = FileState()
        return self.files[name]

    def _pending_bytes(self):
        return sum(ln.nbytes for ln in self.pending)

    def _apply_backpressure(self):
        # 6.1-6.3: an invariant of the buffer - drop from the FRONT (oldest)
        # until the buffer fits, whatever changed the buffer or the limit.
        while self.pending and self._pending_bytes() > self.spool_max_bytes:
            self.pending.pop(0)
            self.dropped += 1

    def _should_flush(self):
        if not self.pending:
            return False
        if len(self.pending) >= self.max_lines:            # 4.1
            return True
        if self._pending_bytes() >= self.max_bytes:        # 4.2
            return True
        if self.now - self.pending[0].t >= self.max_age_ms:  # 4.3
            return True
        return False

    def _take_batch(self):
        # 4.4 -> collector-api.md section 2: the longest prefix of the buffer
        # the collector would accept as one request - at most max_lines records
        # and at most max_bytes of payload - but always at least one record,
        # since an oversize record is accepted when it travels alone.
        take, total = [], 0
        for ln in self.pending:
            if take and (len(take) >= self.max_lines or total + ln.nbytes > self.max_bytes):
                break
            take.append(ln)
            total += ln.nbytes
        self.pending = self.pending[len(take):]
        return take

    def _flush_all(self):
        # 4.4: repeat while a flush condition still holds.
        while self._should_flush():
            take = self._take_batch()
            batch_id = self.next_batch_id                  # 4.5
            self.next_batch_id += 1
            for ln in take:
                ln.attempts += 1                           # 5.2: 1 on first batch
            self.inflight[batch_id] = Batch(take, self.max_retries)   # 4.6

    # -------------------------------------------------------------- events
    def _read(self, name, t):
        # 2.1-2.3: consume only complete lines, only during an append.
        st = self._file(name)
        while True:
            nl = st.stream.find(b"\n", st.read_offset)
            if nl == -1:
                break
            raw = bytes(st.stream[st.read_offset:nl])
            st.read_offset = nl + 1
            self.pending.append(
                Line(raw.decode("utf-8"), name, st.gen, st.read_offset, t))
        self._apply_backpressure()

    def op_config(self, rec):
        # 9: the shipper reloads on SIGHUP, so a capture may carry further
        # config records. New limits take effect where the record is applied.
        self._advance(rec)
        self._load_config(rec)

    def op_append(self, rec):
        self._advance(rec)
        st = self._file(rec["file"])
        st.stream.extend(rec["data"].encode("utf-8"))
        # 2.2: a consumed line is stamped with the clock as it stands.
        self._read(rec["file"], self.now)

    def op_rotate(self, rec):
        # 3.1-3.3: new empty stream, offsets reset, pending lines survive but
        # their generation no longer matches so acks cannot move the new stream.
        self._advance(rec)
        st = self._file(rec["file"])
        st.stream = bytearray()
        st.read_offset = 0
        st.acked_offset = 0
        st.gen += 1

    def op_tick(self, rec):
        self._advance(rec)

    def op_restart(self, rec):
        # 7.1-7.2
        self._advance(rec)
        self.pending = []
        self.inflight = {}
        for st in self.files.values():
            st.read_offset = st.acked_offset

    def op_response(self, rec):
        self._advance(rec)
        batch_id = rec["batch"]
        if batch_id not in self.inflight:                  # 5.5
            return
        batch = self.inflight.pop(batch_id)
        lines = batch.lines
        status = rec["status"]

        if status == 200:                                  # 5.1
            self.delivered.append(
                {"id": batch_id, "lines": [ln.text for ln in lines]})
            for ln in lines:
                st = self._file(ln.file)
                if ln.gen == st.gen:                       # 3.3
                    st.acked_offset = max(st.acked_offset, ln.offset)
        elif status in RETRY_STATUSES:                     # 5.2-5.3
            requeue = []
            for ln in lines:
                ln.attempts += 1
                if ln.attempts > batch.budget:             # 5.3 + collector-api 3
                    self.dlq.append(ln.text)
                else:
                    requeue.append(ln)
            self.pending = requeue + self.pending
            self._apply_backpressure()
        elif status in PERMANENT_STATUSES:                 # 5.4
            self.dlq.extend(ln.text for ln in lines)
        else:
            raise ValueError("unknown status %r" % (status,))

    # --------------------------------------------------------------- drive
    def report(self):
        return {
            "delivered": self.delivered,
            "dlq": self.dlq,
            "dropped": self.dropped,
            "pending": [ln.text for ln in self.pending],
            "offsets": {
                name: {"read": st.read_offset, "acked": st.acked_offset}
                for name, st in sorted(self.files.items())
            },
        }


HANDLERS = {
    "config": "op_config",
    "append": "op_append",
    "rotate": "op_rotate",
    "tick": "op_tick",
    "restart": "op_restart",
    "response": "op_response",
}


def parse_session(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("session must begin with a config record")
    return records[0], records[1:]


def replay(config, records):
    sh = Shipper(config)
    for rec in records:
        op = rec["op"]
        if op == "end":                                    # 8.1: no final flush
            break
        handler = HANDLERS.get(op)
        if handler is None:
            raise ValueError("unknown op %r" % (op,))
        getattr(sh, handler)(rec)
        sh._apply_backpressure()                           # 6.3: an invariant
        sh._flush_all()                                    # 4: after every event
    return sh.report()


def replay_text(text):
    config, records = parse_session(text)
    return replay(config, records)
