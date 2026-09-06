#!/usr/bin/env python3
"""Prove the cruxes bite, by building the wrong implementations on purpose.

A crux is only worth anything if the plausible-but-wrong reading of the task is
actually punished by the test suite. The only way to show that mechanically is
to build the wrong implementations and run the tests against them.

Each variant below is a wrong default someone really does write:

  naive transcription   the pre-corpus decoder: two digits, one frozen table,
                        `tested_on` accepted and ignored, and a single numeric
                        ordering used for the comparison
  monotonic liquid      the liquid numerals treated as one cumulative ladder,
                        so IPX7 is taken to cover IPX5
  dual mark per code    a dual marking evaluated one code at a time instead of
                        unioned position by position
  digits only           the X placeholder and the letters treated as malformed
  current edition       every marking read against the current edition, whatever
                        the date of test
  access is cosmetic    the additional letter stored but never derived from the
                        first numeral
  letter wins downward  an additional letter below the access implied by the
                        first numeral accepted instead of refused

Every variant except the first is the reference engine with one behaviour
replaced, so a failure can only come from that behaviour.

  bitten     at least one test failed  -> the crux is enforced by the suite
  SURVIVOR   every test still passed   -> the wrong default is not punished

Exit status is 0 only when every variant is bitten. This script does not ship
in the task image, and it contains no answers that are not already in
environment/docs.
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


# --------------------------------------------------------------------------
# Variant 1: what the task looks like to someone who never opens environment/.
# --------------------------------------------------------------------------
NAIVE = '''
"""IP code decoder - two digits, one table, one ordering."""
from __future__ import annotations

SOLID = {0: "none", 1: "solid-1", 2: "solid-2", 3: "solid-3", 4: "solid-4",
         5: "dust-protected", 6: "dust-tight"}
LIQ = {0: "none", 1: "drip", 2: "drip-15", 3: "spray", 4: "splash", 5: "jet",
       6: "powerful-jet", 7: "immersion-1m", 8: "submerged"}
ACCESS = {0: "none", 1: "back-of-hand", 2: "finger", 3: "tool", 4: "wire",
          5: "wire", 6: "wire"}


class IpRatingEngine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def _digits(self, code):
        if not isinstance(code, str):
            raise ValueError("code must be a string")
        text = code.strip().upper()
        if text.startswith("IP"):
            text = text[2:]
        if len(text) < 2 or not text[0].isdigit() or not text[1].isdigit():
            raise ValueError("bad IP code: %r" % code)
        return int(text[0]), int(text[1])

    def describe(self, code, tested_on=None):
        first, second = self._digits(code)
        return {
            "solid": SOLID.get(first, "unknown"),
            "liquid": LIQ.get(second, "unknown"),
            "dust_tight": first == 6,
            "access": ACCESS.get(first, "unknown"),
            "supplementary": None,
            "codes": ["IP%d%d" % (first, second)],
            "edition": "IEC 60529:1989+A2:2013",
        }

    def satisfies(self, mark, requirement):
        want_first, want_second = self._digits(requirement)
        for part in str(mark).split("/"):
            have_first, have_second = self._digits(part)
            if have_first >= want_first and have_second >= want_second:
                return True
        return False

    def covers(self, mark, requirement):
        return self.satisfies(mark, requirement)
'''


# --------------------------------------------------------------------------
# Variants 2..n: the reference engine with exactly one rule replaced. Each
# patch is appended to the reference source, so it rebinds a module global the
# engine looks up at call time.
# --------------------------------------------------------------------------
PATCH_MONOTONIC_LIQUID = '''
# wrong default: the liquid numerals read as one cumulative ladder
LIQUID_COVERS = {n: frozenset(range(n + 1)) for n in range(10)}
'''

PATCH_DUAL_PER_CODE = '''
# wrong default: a dual marking evaluated one code at a time
_reference_satisfies = IpRatingEngine.satisfies


def _per_code(self, mark, requirement):
    if isinstance(mark, str) and "/" in mark:
        return any(_reference_satisfies(self, part, requirement)
                   for part in mark.split("/"))
    return _reference_satisfies(self, mark, requirement)


IpRatingEngine.satisfies = _per_code
'''

PATCH_DIGITS_ONLY = '''
# wrong default: anything but two digits is malformed
_reference_parse_mark = parse_mark


def parse_mark(mark):
    codes = _reference_parse_mark(mark)
    for one in codes:
        if one["first"] is None or one["second"] is None:
            raise ValueError("characteristic numeral must be a digit")
        if one["additional"] is not None or one["supplementary"] is not None:
            raise ValueError("a marking is two digits")
    return codes
'''

PATCH_CURRENT_EDITION = '''
# wrong default: tested_on accepted and ignored, current edition always
_reference_resolve_edition = resolve_edition


def resolve_edition(tested_on=None):
    return _reference_resolve_edition(None)
'''

PATCH_ACCESS_COSMETIC = '''
# wrong default: the additional letter is stored, never derived from a numeral
ACCESS_FROM_NUMERAL = {}
'''

PATCH_LETTER_WINS = '''
# wrong default: an additional letter below the implied access is accepted
_reference_parse_code = _parse_code


def _parse_code(part, whole):
    saved = dict(ACCESS_FROM_NUMERAL)
    ACCESS_FROM_NUMERAL.clear()
    try:
        return _reference_parse_code(part, whole)
    finally:
        ACCESS_FROM_NUMERAL.update(saved)
'''

VARIANTS = [
    ("naive transcription (no environment/ read)", None, NAIVE),
    ("monotonic liquid ladder (crux B)", PATCH_MONOTONIC_LIQUID, None),
    ("dual marking evaluated per code (crux B)", PATCH_DUAL_PER_CODE, None),
    ("X and letters treated as malformed (crux D)", PATCH_DIGITS_ONLY, None),
    ("current edition always (crux I)", PATCH_CURRENT_EDITION, None),
    ("access never derived from the numeral (crux H)", PATCH_ACCESS_COSMETIC, None),
    ("additional letter overrides downward (crux H)", PATCH_LETTER_WINS, None),
]


def run_tests(engine_source, work):
    """Run the suite against one engine source. Returns (passed, failed, ids)."""
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
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=600)

    passed = int((re.search(r"(\d+) passed", result.stdout) or [0, 0])[1])
    failed = int((re.search(r"(\d+) failed", result.stdout) or [0, 0])[1])
    errors = int((re.search(r"(\d+) error", result.stdout) or [0, 0])[1])
    ids = re.findall(r"^FAILED ([^\s]+)", result.stdout, re.M)
    if not ids:
        ids = re.findall(r"^ERROR ([^\s]+)", result.stdout, re.M)
    return passed, failed + errors, ids


def main():
    if not ENGINE.exists():
        print("no reference engine at %s" % ENGINE)
        return 1

    reference = ENGINE.read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    try:
        passed, failed, _ = run_tests(reference, work)
        if failed:
            print("BASELINE BROKEN: the reference engine fails %d of its own "
                  "tests. Nothing below would mean anything." % failed)
            return 1
        total = passed
        print("baseline: reference engine passes all %d tests\n" % total)

        survivors = []
        for label, patch, replacement in VARIANTS:
            source = replacement if replacement else reference + patch
            passed, failed, ids = run_tests(source, work)
            if failed:
                print("bitten     %-48s %3d/%d failed" % (label, failed, total))
                for one in sorted(set(ids))[:4]:
                    print("             %s" % one)
                if len(set(ids)) > 4:
                    print("             ... and %d more" % (len(set(ids)) - 4))
            else:
                survivors.append(label)
                print("SURVIVOR   %-48s all %d passed" % (label, passed))
            print()

        if survivors:
            print("A survivor is a wrong default the suite does not punish. "
                  "Each one needs a test.")
            return 1
        print("every wrong default is punished by the suite")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
