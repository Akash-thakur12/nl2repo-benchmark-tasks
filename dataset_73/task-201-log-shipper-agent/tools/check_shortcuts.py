#!/usr/bin/env python3
"""Prove the corpus is discriminating rather than asserting that it is.

Each entry below is a plausible near-miss: a reading of the specification a
competent engineer could land on. For every one of them this script asserts

  1. it still reproduces environment/samples/expected.json exactly, and
  2. at least one held-out session in tests/sessions catches it.

A shortcut that fails (1) is not evidence of anything - the visible samples
would already have rejected it. A shortcut that survives (2) is a hole in the
held-out corpus and the corpus must grow to cover it.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_shipper as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"


# --------------------------------------------------------------- mutations
def m_lines_only(S):
    class M(S):
        def _should_flush(self):
            return bool(self.pending) and len(self.pending) >= self.max_lines
    return M


def m_no_age_trigger(S):
    class M(S):
        def _should_flush(self):
            if not self.pending:
                return False
            return (len(self.pending) >= self.max_lines
                    or self._pending_bytes() >= self.max_bytes)
    return M


def m_age_from_newest(S):
    class M(S):
        def _should_flush(self):
            if not self.pending:
                return False
            if len(self.pending) >= self.max_lines:
                return True
            if self._pending_bytes() >= self.max_bytes:
                return True
            return self.now - self.pending[-1].t >= self.max_age_ms
    return M


def m_consume_fragment(S):
    class M(S):
        def _read(self, name, t):
            st = self._file(name)
            chunk = bytes(st.stream[st.read_offset:])
            if not chunk:
                self._apply_backpressure()
                return
            parts = chunk.split(b"\n")
            if parts and parts[-1] == b"":
                parts.pop()
            st.read_offset = len(st.stream)
            off = st.read_offset
            for raw in parts:
                self.pending.append(ref.Line(raw.decode("utf-8"), name, st.gen, off, t))
            self._apply_backpressure()
    return M


def m_rotate_clears_pending(S):
    class M(S):
        def op_rotate(self, rec):
            super().op_rotate(rec)
            self.pending = []
    return M


def m_rotate_ignores_generation(S):
    class M(S):
        def op_rotate(self, rec):
            self.now = rec["t"]
            st = self._file(rec["file"])
            st.stream = bytearray()
            st.read_offset = 0
            st.acked_offset = 0
            # generation deliberately not bumped
    return M


def m_requeue_at_back(S):
    class M(S):
        def op_response(self, rec):
            self.now = rec["t"]
            bid = rec["batch"]
            if bid not in self.inflight:
                return
            lines = self.inflight.pop(bid)
            status = rec["status"]
            if status == 200:
                self.delivered.append({"id": bid, "lines": [l.text for l in lines]})
                for ln in lines:
                    st = self._file(ln.file)
                    if ln.gen == st.gen:
                        st.acked_offset = max(st.acked_offset, ln.offset)
            elif status in ref.RETRY_STATUSES:
                keep = []
                for ln in lines:
                    ln.attempts += 1
                    if ln.attempts > self.max_retries:
                        self.dlq.append(ln.text)
                    else:
                        keep.append(ln)
                self.pending = self.pending + keep      # back, not front
                self._apply_backpressure()
            else:
                self.dlq.extend(l.text for l in lines)
    return M


def m_retry_off_by_one(S):
    class M(S):
        def op_response(self, rec):
            if rec["status"] in ref.RETRY_STATUSES and rec["batch"] in self.inflight:
                self.now = rec["t"]
                lines = self.inflight.pop(rec["batch"])
                keep = []
                for ln in lines:
                    ln.attempts += 1
                    if ln.attempts >= self.max_retries:   # >= instead of >
                        self.dlq.append(ln.text)
                    else:
                        keep.append(ln)
                self.pending = keep + self.pending
                self._apply_backpressure()
                return
            super().op_response(rec)
    return M


def m_permanent_is_retry(S):
    class M(S):
        def op_response(self, rec):
            if rec["status"] in ref.PERMANENT_STATUSES:
                rec = dict(rec, status=503)
            super().op_response(rec)
    return M


def m_unknown_batch_applied(S):
    class M(S):
        def op_response(self, rec):
            if rec["batch"] not in self.inflight and rec["status"] == 200:
                self.now = rec["t"]
                self.delivered.append({"id": rec["batch"], "lines": []})
                return
            super().op_response(rec)
    return M


def m_drop_newest(S):
    class M(S):
        def _apply_backpressure(self):
            while self.pending and self._pending_bytes() > self.spool_max_bytes:
                self.pending.pop()                        # newest, not oldest
                self.dropped += 1
    return M


def m_bytes_without_newline(S):
    class M(S):
        def _pending_bytes(self):
            return sum(len(l.text.encode("utf-8")) for l in self.pending)
    return M


def m_bytes_as_chars(S):
    class M(S):
        def _pending_bytes(self):
            return sum(len(l.text) + 1 for l in self.pending)
    return M


def m_no_backpressure_on_requeue(S):
    class M(S):
        def op_response(self, rec):
            if rec["status"] in ref.RETRY_STATUSES and rec["batch"] in self.inflight:
                self.now = rec["t"]
                lines = self.inflight.pop(rec["batch"])
                keep = []
                for ln in lines:
                    ln.attempts += 1
                    if ln.attempts > self.max_retries:
                        self.dlq.append(ln.text)
                    else:
                        keep.append(ln)
                self.pending = keep + self.pending        # no backpressure call
                return
            super().op_response(rec)
    return M


def m_restart_keeps_read_offset(S):
    class M(S):
        def op_restart(self, rec):
            self.now = rec["t"]
            self.pending = []
            self.inflight = {}
            # read_offset deliberately not rewound to acked_offset
    return M


def m_restart_keeps_inflight(S):
    class M(S):
        def op_restart(self, rec):
            self.now = rec["t"]
            self.pending = []
            for st in self.files.values():
                st.read_offset = st.acked_offset
            # inflight batches deliberately kept
    return M


def m_flush_whole_buffer(S):
    class M(S):
        def _flush_all(self):
            while self._should_flush():
                take = self.pending                       # ignores the max_lines cap
                self.pending = []
                bid = self.next_batch_id
                self.next_batch_id += 1
                for ln in take:
                    ln.attempts += 1
                self.inflight[bid] = take
    return M


def m_final_flush(S):
    class M(S):
        pass

    def replay(config, records):
        sh = M(config)
        for rec in records:
            if rec["op"] == "end":
                sh.pending and sh._flush_all_force()      # flush at end
                break
            getattr(sh, ref.HANDLERS[rec["op"]])(rec)
            sh._flush_all()
        return sh.report()

    def _flush_all_force(self):
        while self.pending:
            take = self.pending[:self.max_lines]
            self.pending = self.pending[self.max_lines:]
            bid = self.next_batch_id
            self.next_batch_id += 1
            for ln in take:
                ln.attempts += 1
            self.inflight[bid] = take

    M._flush_all_force = _flush_all_force
    M._custom_replay = staticmethod(replay)
    return M


def m_delivered_sorted_by_id(S):
    class M(S):
        def report(self):
            out = super().report()
            out["delivered"] = sorted(out["delivered"], key=lambda b: b["id"])
            return out
    return M


def m_ack_ignores_max(S):
    class M(S):
        def op_response(self, rec):
            if rec["status"] == 200 and rec["batch"] in self.inflight:
                self.now = rec["t"]
                bid = rec["batch"]
                lines = self.inflight.pop(bid)
                self.delivered.append({"id": bid, "lines": [l.text for l in lines]})
                for ln in lines:
                    st = self._file(ln.file)
                    if ln.gen == st.gen:
                        st.acked_offset = ln.offset       # no max(), last wins
                return
            super().op_response(rec)
    return M


SHORTCUTS = [
    ("flush only on max_lines, ignoring bytes and age", m_lines_only),
    ("ignore the max_age_ms flush trigger", m_no_age_trigger),
    ("measure batch age from the newest line", m_age_from_newest),
    ("consume a trailing fragment as a complete line", m_consume_fragment),
    ("clear the pending buffer on rotation", m_rotate_clears_pending),
    ("let a pre-rotation ack move the new stream's offset", m_rotate_ignores_generation),
    ("requeue a failed batch at the back of the buffer", m_requeue_at_back),
    ("dead-letter at attempts >= max_retries", m_retry_off_by_one),
    ("treat a permanent reject as a transient failure", m_permanent_is_retry),
    ("act on a response for an unknown batch id", m_unknown_batch_applied),
    ("drop the newest lines under backpressure", m_drop_newest),
    ("count spool bytes without the stripped newline", m_bytes_without_newline),
    ("count spool bytes as characters rather than UTF-8 bytes", m_bytes_as_chars),
    ("skip backpressure for requeued lines", m_no_backpressure_on_requeue),
    ("keep read_offset across a restart", m_restart_keeps_read_offset),
    ("keep in-flight batches across a restart", m_restart_keeps_inflight),
    ("flush the whole buffer as one batch", m_flush_whole_buffer),
    ("flush what is pending when the session ends", m_final_flush),
    ("report delivered batches in id order", m_delivered_sorted_by_id),
    ("advance acked_offset without taking the maximum", m_ack_ignores_max),
]


# ------------------------------------------------------------------ driver
def run(cls, text):
    config, records = ref.parse_session(text)
    custom = getattr(cls, "_custom_replay", None)
    if custom is not None:
        return custom(config, records)
    sh = cls(config)
    for rec in records:
        if rec["op"] == "end":
            break
        getattr(sh, ref.HANDLERS[rec["op"]])(rec)
        sh._flush_all()
    return sh.report()


def main():
    sample_files = sorted(SAMPLES.glob("*.session"))
    held_files = sorted(HELD_OUT.glob("*.session"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    # sanity: the reference itself must reproduce expected.json
    for f in sample_files:
        got = ref.replay_text(f.read_text(encoding="utf-8"))
        assert got == expected[f.stem], "reference disagrees with expected.json on %s" % f.stem

    held_truth = {f.stem: ref.replay_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad_samples, uncaught, rows = [], [], []
    for label, make in SHORTCUTS:
        cls = make(ref.Shipper)

        passes_samples = True
        for f in sample_files:
            try:
                got = run(cls, f.read_text(encoding="utf-8"))
            except Exception:
                passes_samples = False
                break
            if got != expected[f.stem]:
                passes_samples = False
                break

        caught = []
        for f in held_files:
            try:
                got = run(cls, f.read_text(encoding="utf-8"))
            except Exception:
                caught.append(f.stem)
                continue
            if got != held_truth[f.stem]:
                caught.append(f.stem)

        rows.append((label, passes_samples, caught))
        if not passes_samples:
            bad_samples.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        print("%-*s  %-8s  %s" % (
            width, label, "pass" if ok else "FAIL",
            ("%d: %s" % (len(caught), ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")))
            if caught else "NONE"))

    print()
    print("shortcuts            : %d" % len(rows))
    print("reproduce samples    : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out   : %d" % sum(1 for r in rows if r[2]))

    if bad_samples:
        print("\nNot discriminating - these are already rejected by the visible samples,")
        print("so they are not evidence the held-out corpus is doing any work:")
        for lb in bad_samples:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out session:")
        for lb in uncaught:
            print("  -", lb)
    if bad_samples or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
