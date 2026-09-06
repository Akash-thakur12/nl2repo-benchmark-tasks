#!/usr/bin/env python3
"""Prove that each crux in this task actually bites.

A crux is only worth anything if the *plausible wrong reading* of the
specification fails the suite. This script writes out working engines that take
those wrong readings -- the ones the retired AN-0417 note and the
`environment/tools/rollover_diag.py` field diagnostic recommend -- and runs the
real test suite against each.

Variants
--------

  skimmer   all four wrong readings at once: the implementation you get by
            reading instruction.md, running rollover_diag.py, and believing its
            ROOT CAUSE line. This is the calibration case: it must score
            non-zero (reward has to stay continuous) and it must score below
            the task's 0.5 pass threshold.

  crux-C    era resolution against the MOST RECENT anchor not later than the
            reference date, with no grace window (AN-0417 s4).
  crux-E    tow_sec = tow_count * 6, i.e. the count names this subframe rather
            than the next one, and no range check (AN-0417 s2.1).
  crux-I    a single fixed GPS-UTC offset of 18 s (AN-0417 s3).
  crux-H    WNa decoded with the 1024-week modulus and the era rule, instead of
            modulo 256 pivoted on the record's own ephemeris week (AN-0417 s5).

Each single-crux variant is otherwise correct, so the tests it fails are
attributable to that crux alone.

Exit status is 0 when every variant fails, and when the skimmer variant lands
in the expected partial-credit band. This script does not ship in the task
image and contains no answers that are not already in environment/docs/.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
ENGINE = TASK / "solution" / "engine" / "engine.py"
TESTS = TASK / "tests" / "test_outputs.py"

SKIMMER_BAND = (0.20, 0.50)

# --- the wrong readings, as source rewrites of the reference engine ----------

WRONG_ERA = ('''    def to_date(self, week, dow=0):
        # AN-0417 s4: most recent anchor not later than the reference date,
        # comparison window exactly 1024 weeks, no slop.
        if not isinstance(week, int) or isinstance(week, bool):
            raise ValidationError("week must be an int")
        if not 0 <= week <= 65535:
            raise ValidationError("week out of range")
        if not isinstance(dow, int) or isinstance(dow, bool):
            raise ValidationError("dow must be an int")
        if not 0 <= dow <= 6:
            raise ValidationError("dow out of range")
        started = [pair for pair in EPOCHS if pair[1] <= self._ref] or [EPOCHS[0]]
        base_week, anchor = started[-1]
        offset = (week - base_week) % 1024
        return anchor + dt.timedelta(weeks=offset, days=dow)
''')

WRONG_TOW = ("""        # AN-0417 s2.1: the count is this subframe's own time, in 6 s units,
        # and the 17-bit field needs no range check.
        if not isinstance(tow_count, int) or isinstance(tow_count, bool):
            raise ValidationError("tow_count must be an int")
        week = self.resolve_week(raw_week, source, current_week)
        sow = (tow_count * SUBFRAME_SECONDS) % SECONDS_PER_WEEK
""")

#: the same reading on the inverse path
WRONG_TOW_INVERSE = (
    "        tow_count = (sow // SUBFRAME_SECONDS) % TOW_COUNT_MODULUS\n")

WRONG_LEAP = ('''    def leap_offset(self, when, scale="utc"):
        # AN-0417 s3: a single constant is sufficient.
        if scale not in ("utc", "gps"):
            raise ValidationError("scale must be 'utc' or 'gps'")
        self._as_datetime(when)
        return 18
''')

WRONG_WNA = ('''            # AN-0417 s5: same 1024-week modulus and the same era rule as WN.
            return self.from_date(self.to_date(raw % 1024, 0))[0]
''')


def _cut(source, start_marker, end_marker, replacement):
    """Replace the block from ``start_marker`` up to ``end_marker``."""
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[:start] + replacement + source[end:]


def apply_era(source):
    return _cut(source, "    def to_date(self, week, dow=0):",
                "    def from_date(self, d):", WRONG_ERA + "\n")


def apply_tow(source):
    source = _cut(source, "        if not isinstance(tow_count, int)",
                  "        origin = dt.datetime(epoch.year", WRONG_TOW + "\n")
    return _cut(source, "        tow_count = (sow // SUBFRAME_SECONDS",
                "        return week, tow_count", WRONG_TOW_INVERSE)


def apply_leap(source):
    return _cut(source, '    def leap_offset(self, when, scale="utc"):',
                "    # ------------------------------------------------------------ time decode",
                WRONG_LEAP + "\n")


def apply_wna(source):
    start = source.index("            if current_week is None:")
    end = source.index("        # LNAV: the era rule", start)
    return source[:start] + WRONG_WNA + "\n" + source[end:]


VARIANTS = [
    ("crux-C  most-recent anchor, no grace", [apply_era]),
    ("crux-E  tow_count * 6, no range check", [apply_tow]),
    ("crux-I  fixed 18 s GPS-UTC offset", [apply_leap]),
    ("crux-H  WNa modulo 1024 via the era rule", [apply_wna]),
    ("skimmer all four AN-0417 readings", [apply_era, apply_tow, apply_leap, apply_wna]),
]


def run_tests(engine_source, work):
    """Run the real suite against one rewritten engine; return (passed, total, names)."""
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(ENGINE.parent, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "engine.py").write_text(engine_source, encoding="utf-8")

    environment = dict(os.environ)
    environment["ENGINE_DIR"] = str(package)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-v", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True, timeout=600)

    outcomes = re.findall(r"::(\S+) (PASSED|FAILED|ERROR)\b", result.stdout)
    passed = sum(1 for _, status in outcomes if status == "PASSED")
    failing = sorted({name.split("[")[0] for name, status in outcomes if status != "PASSED"})
    return passed, len(outcomes), failing


def main():
    if not ENGINE.exists():
        print("no reference engine at %s" % ENGINE)
        return 1

    source = ENGINE.read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    problems = []
    try:
        passed, total, _ = run_tests(source, work)
        if total == 0 or passed != total:
            print("BASELINE BROKEN: the reference engine scores %d/%d against its "
                  "own tests. Nothing below would mean anything." % (passed, total))
            return 1
        print("baseline: reference engine %d/%d\n" % (passed, total))

        for label, steps in VARIANTS:
            mutated = source
            for step in steps:
                mutated = step(mutated)
            passed, total, failing = run_tests(mutated, work)
            score = passed / total if total else 0.0
            print("%-42s %3d/%-3d  score %.3f" % (label, passed, total, score))
            if passed == total:
                print("    NOT CAUGHT -- no test depends on this rule")
                problems.append(label)
            else:
                for name in failing[:8]:
                    print("    caught by %s" % name)
                if len(failing) > 8:
                    print("    ... and %d more" % (len(failing) - 8))
            if label.startswith("skimmer"):
                low, high = SKIMMER_BAND
                if not low <= score < high:
                    print("    CALIBRATION OFF -- expected the skimmer in [%.2f, %.2f)"
                          % (low, high))
                    problems.append(label + " (calibration)")
                else:
                    print("    calibration ok: partial credit, below the 0.5 threshold")
            print()

        if problems:
            print("FAIL: %s" % "; ".join(problems))
            return 1
        print("OK: every wrong-default reading is caught, and the skimmer lands "
              "in the partial-credit band below the pass threshold.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
