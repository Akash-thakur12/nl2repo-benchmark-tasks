#!/usr/bin/env python3
"""Prove the cruxes bite, by building the wrong-default engines on purpose.

A crux is only worth anything if the plausible-but-wrong implementation of it
actually fails the suite. This script takes the reference engine and rewrites it
into each wrong default a real implementer would plausibly land on - the
backward roll, the truncated timestamp, the hardcoded 16:00 deadline, the fixed
UTC offset, last-row-wins price selection, today's best price instead of the one
in force at the strike, no corporate actions at all, actions applied without an
upper bound, the inclusive ex-date, the multiply that should be a divide,
single-stage rounding, and price age counted in calendar days.

Each variant is run against the full suite. For every one of them we require:

  * at least one test fails (the crux is load-bearing), and
  * a good number of tests still pass (reward stays continuous - a wrong turn
    on one rule does not zero the whole submission).

The "legacy" variant is the engine this task shipped with before the cruxes were
added: the naive transcription of the old specification. It is the floor of the
score band, and it is expected to pass the seven original tests and nothing else.

No secrets here - every variant is a damaged copy of solution/engine, which the
buyer already has.

  python tools/check_crux.py
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
ENGINE = TASK / "solution" / "engine"
TESTS = TASK / "tests" / "test_outputs.py"

LEGACY_ENGINE = '''
from __future__ import annotations
import datetime as dt


class StaleAuthorityError(Exception):
    pass


class FundNavEngine:
    """The pre-crux implementation: latest price dated on or before the cutoff."""

    def __init__(self, config=None):
        prices = (config or {}).get("prices", [])
        self._prices = sorted(prices, key=lambda dp: dp[0])

    def reset(self):
        self._prices = []

    def configure(self, options):
        if "prices" in options:
            self._prices = sorted(options["prices"], key=lambda dp: dp[0])

    def add_price(self, date_str, price, published_at=None):
        self._prices.append((date_str, price))
        self._prices.sort(key=lambda dp: dp[0])

    def _eligible(self, cutoff):
        c = dt.date.fromisoformat(str(cutoff)[:10])
        return [(d, p) for d, p in self._prices if dt.date.fromisoformat(str(d)[:10]) <= c]

    def resolve_valuation_date(self, cutoff):
        return dt.date.fromisoformat(str(cutoff)[:10])

    def nav_per_unit(self, cutoff):
        elig = self._eligible(cutoff)
        if not elig:
            raise StaleAuthorityError("no price on or before %s" % cutoff)
        return round(float(elig[-1][1]), 4)

    def nav(self, cutoff, units):
        elig = self._eligible(cutoff)
        if not elig:
            raise StaleAuthorityError("no price on or before %s" % cutoff)
        return round(float(elig[-1][1]) * units, 4)

    def is_stale(self, cutoff):
        return not self._eligible(cutoff)
'''

#: name -> list of (search, replace) rewrites applied to the reference engine.
#: Every rewrite must match, or the variant is reported as broken rather than
#: quietly passing.
VARIANTS = {
    "backward roll to the previous session": [
        ("            if self._is_session(day):\n                return day\n"
         "            day += dt.timedelta(days=1)",
         "            if self._is_session(day):\n                return day\n"
         "            day -= dt.timedelta(days=1)"),
    ],
    "timestamp truncated to its date": [
        ('        text = str(cutoff).strip()\n        if "T" not in text',
         '        text = str(cutoff).strip().split("T")[0]\n        if "T" not in text'),
    ],
    "deadline hardcoded at 16:00": [
        ("_EARLY_DEADLINE = (13, 0, 0)", "_EARLY_DEADLINE = (16, 0, 0)"),
    ],
    "UTC offset hardcoded at -05:00": [
        ("        for start, end, offset in self._offsets:",
         "        for start, end, offset in []:"),
    ],
    "last row loaded wins": [
        ('                   and (r["published_at"] is None or r["published_at"] <= strike)]',
         "                   ]"),
        ('        return max(same_day, key=lambda r: (r["published_at"] or floor, r["seq"]))',
         '        return max(same_day, key=lambda r: r["seq"])'),
    ],
    "newest record wins, ignoring the strike": [
        ('                   and (r["published_at"] is None or r["published_at"] <= strike)]',
         "                   ]"),
    ],
    "corporate actions ignored": [
        ("            if price_date < ex_date <= valuation_date:",
         "            if False:"),
    ],
    "corporate actions unbounded above": [
        ("            if price_date < ex_date <= valuation_date:",
         "            if price_date < ex_date:"),
    ],
    "ex-date treated as inclusive below": [
        ("            if price_date < ex_date <= valuation_date:",
         "            if price_date <= ex_date <= valuation_date:"),
    ],
    "restatement multiplies instead of dividing": [
        ('        return record["price"] / divisor', '        return record["price"] * divisor'),
    ],
    "single-stage rounding of price times units": [
        ("        per_unit = self._price_in_force(cutoff).quantize(_UNIT, rounding=ROUND_HALF_UP)\n"
         "        value = (per_unit * _dec(units)).quantize(_CENT, rounding=ROUND_HALF_UP)",
         "        raw = self._price_in_force(cutoff)\n"
         "        value = (raw * _dec(units)).quantize(_CENT, rounding=ROUND_HALF_UP)"),
    ],
    "price age counted in calendar days": [
        ("            if self._is_session(day):\n                count += 1",
         "            if True:\n                count += 1"),
    ],
}


def run_suite(source, work):
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(ENGINE, package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "engine.py").write_text(source, encoding="utf-8")

    env = {"ENGINE_DIR": str(package), "PYTHONDONTWRITEBYTECODE": "1"}
    import os
    environment = dict(os.environ)
    environment.update(env)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True, timeout=600)
    passed = len(re.findall(r"^\.", result.stdout, re.M))
    m_pass = re.search(r"(\d+) passed", result.stdout)
    m_fail = re.search(r"(\d+) failed", result.stdout)
    passed = int(m_pass.group(1)) if m_pass else 0
    failed = int(m_fail.group(1)) if m_fail else 0
    return passed, failed


def main():
    reference = (ENGINE / "engine.py").read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    problems = []
    try:
        total_pass, total_fail = run_suite(reference, work)
        total = total_pass + total_fail
        print("reference engine: %d/%d passed" % (total_pass, total))
        if total_fail:
            print("BASELINE BROKEN - nothing below means anything.")
            return 1

        rows = []
        legacy_pass, legacy_fail = run_suite(LEGACY_ENGINE, work)
        rows.append(("legacy pre-crux engine", legacy_pass, legacy_fail))
        if legacy_fail == 0:
            problems.append("legacy pre-crux engine still passes everything")

        for name, rewrites in VARIANTS.items():
            source = reference
            for search, replace in rewrites:
                if search not in source:
                    problems.append("%s: rewrite did not apply" % name)
                    source = None
                    break
                source = source.replace(search, replace, 1)
            if source is None:
                continue
            passed, failed = run_suite(source, work)
            rows.append((name, passed, failed))
            if failed == 0:
                problems.append("%s: no test noticed" % name)
            if passed < 7:
                problems.append("%s: only %d tests survive - reward is not "
                                "continuous here" % (name, passed))

        width = max(len(r[0]) for r in rows)
        print()
        print("%-*s  %6s  %6s" % (width, "wrong default", "passed", "failed"))
        for name, passed, failed in rows:
            print("%-*s  %6d  %6d" % (width, name, passed, failed))

        print()
        if problems:
            for line in problems:
                print("PROBLEM: %s" % line)
            return 1
        print("every wrong default is caught, and every one of them still scores "
              "partial credit: the cruxes bite and the reward stays continuous.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
