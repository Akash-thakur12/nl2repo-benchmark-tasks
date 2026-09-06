#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out session catches it.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_backfill as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"


def m_chunk_overruns_end(R):
    class M(R):
        def _next_chunk(self):
            first = self.checkpoint
            return first, first + self.chunk_size      # ignores end
    return M


def m_resume_not_clamped(R):
    class M(R):
        def __init__(self, config):
            super().__init__(config)
            self.checkpoint = config.get("resume_from", self.start)
    return M


def m_checkpoint_advances_on_failure(R):
    class M(R):
        def op_attempt(self, record):
            before = self.checkpoint
            super().op_attempt(record)
            if self.attempts and self.attempts[-1]["outcome"] == "fail" \
                    and self.checkpoint == before:
                self.checkpoint = self.attempts[-1]["to"]
    return M


def m_window_inclusive(R):
    class M(R):
        def _rate_allows(self):
            live = [t for t in self.recent if self.now - t <= self.window]
            self.recent = live
            return len(live) < self.max_per_window
    return M


def m_window_allows_one_more(R):
    class M(R):
        def _rate_allows(self):
            live = [t for t in self.recent if self.now - t < self.window]
            self.recent = live
            return len(live) <= self.max_per_window
    return M


def m_failures_do_not_count_against_rate(R):
    class M(R):
        def op_attempt(self, record):
            before = len(self.recent)
            super().op_attempt(record)
            if self.attempts and self.attempts[-1]["outcome"] == "fail" \
                    and len(self.recent) > before:
                self.recent.pop()
    return M


def m_wait_not_counted(R):
    class M(R):
        def op_attempt(self, record):
            before = self.waits
            super().op_attempt(record)
            self.waits = before
    return M


def m_wait_skips_chunk(R):
    class M(R):
        def op_attempt(self, record):
            self.now = record["t"]
            if self.halted or self.paused or self.finished:
                return
            if not self._rate_allows():
                self.waits += 1
                self.checkpoint = min(self.checkpoint + self.chunk_size, self.end)
                return
            super().op_attempt(record)
    return M


def m_halt_at_max_plus_one(R):
    class M(R):
        def op_attempt(self, record):
            was = self.halted
            super().op_attempt(record)
            if not was and self.halted and self.failures == self.max_attempts:
                self.halted = False                    # one more go than allowed
    return M


def m_failures_never_reset(R):
    class M(R):
        def op_attempt(self, record):
            before = self.failures
            super().op_attempt(record)
            if self.attempts and self.attempts[-1]["outcome"] == "ok":
                self.failures = before                 # a success forgives nothing
    return M


def m_resume_clears_halt(R):
    class M(R):
        def op_resume(self, record):
            super().op_resume(record)
            self.halted = False
    return M


def m_pause_clears_failures(R):
    class M(R):
        def op_pause(self, record):
            super().op_pause(record)
            self.failures = 0
    return M


def m_pause_counts_as_wait(R):
    class M(R):
        def op_attempt(self, record):
            if self.paused and not self.halted and not self.finished:
                self.now = record["t"]
                self.waits += 1
                return
            super().op_attempt(record)
    return M


def m_percent_rounds(R):
    class M(R):
        def report(self):
            out = super().report()
            total = out["state"]["total"]
            done = out["state"]["done"]
            if total:
                out["state"]["percent"] = (done * 200 + total) // (2 * total)
            return out
    return M


def m_empty_range_zero_percent(R):
    class M(R):
        def report(self):
            out = super().report()
            if out["state"]["total"] == 0:
                out["state"]["percent"] = 0
            return out
    return M


def m_outcomes_run_out_as_failure(R):
    class M(R):
        def _outcome(self):
            if self.taken < len(self.outcomes):
                result = self.outcomes[self.taken]
            else:
                result = "fail"
            self.taken += 1
            return result
    return M


def m_outcome_index_per_chunk(R):
    class M(R):
        def op_attempt(self, record):
            before = self.checkpoint
            super().op_attempt(record)
            if self.checkpoint == before and self.attempts \
                    and self.attempts[-1]["outcome"] == "fail":
                self.taken -= 1                        # a retry re-reads the same
    return M


SHORTCUTS = [
    ("a chunk may run past the end of the range", m_chunk_overruns_end),
    ("a resume point below the range is not raised to it", m_resume_not_clamped),
    ("a failed attempt still advances the checkpoint", m_checkpoint_advances_on_failure),
    ("the rate window is inclusive at its boundary", m_window_inclusive),
    ("the rate window allows one attempt too many", m_window_allows_one_more),
    ("a failed attempt does not count against the rate", m_failures_do_not_count_against_rate),
    ("a wait is not counted", m_wait_not_counted),
    ("a rate-limited chunk is skipped rather than retried", m_wait_skips_chunk),
    ("the job halts one attempt later than it should", m_halt_at_max_plus_one),
    ("a success does not reset the failure count", m_failures_never_reset),
    ("resuming clears the halt", m_resume_clears_halt),
    ("pausing clears the failure count", m_pause_clears_failures),
    ("an attempt while paused counts as a wait", m_pause_counts_as_wait),
    ("the percentage is rounded rather than floored", m_percent_rounds),
    ("an empty range reports nought per cent", m_empty_range_zero_percent),
    ("outcomes past the end of the list are failures", m_outcomes_run_out_as_failure),
    ("a retry re-reads the same entry from the outcomes list", m_outcome_index_per_chunk),
]


def run(cls, text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    runner = cls(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        getattr(runner, ref.HANDLERS[record["op"]])(record)
    return runner.report()


def main():
    sample_files = sorted(SAMPLES.glob("*.session"))
    held_files = sorted(HELD_OUT.glob("*.session"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    baseline = run(ref.Runner, sample_files[0].read_text(encoding="utf-8"))
    assert baseline == expected[sample_files[0].stem], \
        "the mutation harness does not reproduce the reference on its own"

    for f in sample_files:
        assert ref.replay_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.replay_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, make in SHORTCUTS:
        cls = make(ref.Runner)
        ok = True
        for f in sample_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out session:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
