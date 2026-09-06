#!/usr/bin/env python3
"""Measure every task in the delivery set on the things the buyer's gate cares about.

Four numbers per task, all obtained by running code rather than by reading it:

  golden      the reference solution's pass ratio. Anything below 1.0 is a bug in
              the task, not in the model, and would cost the sale outright.
  stub        the starting repository's pass ratio. Anything above 0 means some
              test passes for free.
  tests       the number of independent test functions. This sets the resolution
              of the reward: with six tests the score can only move in 17% steps,
              and the acceptance gate is decided by a 12.5% gap.
  cruxes      which of the A-I difficulty mechanisms the task documents.

Only engine-architecture tasks are scored here. The repo-architecture tasks drive
a command line inside a container and are measured by their own tests/test.sh.
"""
import concurrent.futures
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "dataset_73")
LETTERS = re.compile(r"^\s*(?:crux\s*)?([A-I])\s*[-:.]", re.M | re.I)


def ratio(task, engine_dir):
    """Pass ratio of one engine against the task's own suite."""
    tests = task / "tests" / "test_outputs.py"
    if not tests.exists() or not engine_dir.exists():
        return None
    env = dict(os.environ, ENGINE_DIR=str(engine_dir), PYTHONDONTWRITEBYTECODE="1")
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests), "-q", "--tb=no",
             "-p", "no:cacheprovider"],
            cwd=str(task), env=env, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None
    # Read pytest's own summary rather than counting status words, which appear
    # twice for every failure and would inflate the denominator.
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out.stdout)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out.stdout)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", out.stdout)) else 0
    total = passed + failed + errors
    return passed / total if total else None


def survey(task):
    tests = task / "tests" / "test_outputs.py"
    count = len(set(re.findall(r"^def (test_\w+)", tests.read_text(encoding="utf-8",
                                                                   errors="replace"), re.M))) if tests.exists() else 0
    notes = task / "CRUX.md"
    cruxes = sorted(set(m.upper() for m in LETTERS.findall(
        notes.read_text(encoding="utf-8", errors="replace")))) if notes.exists() else []
    engine = (task / "solution" / "engine").exists()
    return {
        "task": task.name,
        "kind": "engine" if engine else "repo",
        "tests": count,
        "cruxes": cruxes,
        "golden": ratio(task, task / "solution" / "engine") if engine else None,
        "stub": ratio(task, task / "environment" / "engine") if engine else None,
    }


def main():
    tasks = sorted(p for p in ROOT.iterdir() if p.is_dir() and (p / "task.toml").exists())
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(survey, tasks))

    def show(value):
        return "-" if value is None else "%.2f" % value

    print("%-38s %-6s %5s %6s %6s  %s" % ("TASK", "KIND", "TESTS", "GOLD", "STUB", "CRUXES"))
    broken, thin, uncruxed = [], [], []
    for row in rows:
        print("%-38s %-6s %5d %6s %6s  %s"
              % (row["task"], row["kind"], row["tests"], show(row["golden"]),
                 show(row["stub"]), ",".join(row["cruxes"]) or "-"))
        if row["kind"] == "engine" and row["golden"] not in (1.0, None):
            broken.append(row["task"])
        if row["stub"]:
            broken.append(row["task"] + " (stub scores > 0)")
        if row["tests"] < 14:
            thin.append("%s (%d)" % (row["task"], row["tests"]))
        if not row["cruxes"]:
            uncruxed.append(row["task"])

    print("\n%d tasks" % len(rows))
    print("golden not 1.0 or stub not 0 : %d %s" % (len(broken), broken or ""))
    print("fewer than 14 tests          : %d %s" % (len(thin), thin or ""))
    print("no documented crux           : %d" % len(uncruxed))
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
