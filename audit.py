#!/usr/bin/env python3
"""One command that says where every task in the delivery set actually stands.

Written to be run after each hardening batch. Nothing here is taken on trust: the
pass ratios come from running the suites, not from reading a report.

  gold    the reference solution's pass ratio. Below 1.0 the task is broken, and a
          broken task costs the sale outright - the buyer runs the oracle first.
  stub    the starting repository's pass ratio. Above 0 means a test passes for
          free, which shrinks the gap the acceptance gate measures.
  tests   independent test functions. This sets the resolution of the reward:
          with six tests the score moves in 17% steps and the gate is decided by
          a 12.5% gap, so coarse suites cannot express the gap at all.
  crux    the A-I mechanisms the task documents in CRUX.md, plus whether the
          machine-checkable proof (tools/check_crux.py) ships beside it.

Repo-architecture tasks drive a command line inside the task image, so their
pass ratio is not measurable from here; they are listed with their test count and
paperwork, and graded separately with `harbor run -a oracle`.
"""
import concurrent.futures
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    r"C:\Users\user\Downloads\HardTask\work\dataset_73")
# Agents title each crux section in their own voice - "## C - ...",
# "## Crux B (primary), with H - ...", "## A (latent) - ..." - so match the
# letter wherever it opens the heading rather than one house style.
LETTER = re.compile(r"^#{2,3}\s*(?:Crux\s+)?([A-I])", re.M)


def ratio(task, engine):
    tests = task / "tests" / "test_outputs.py"
    if not tests.exists() or not engine.exists():
        return None
    env = dict(os.environ, ENGINE_DIR=str(engine), PYTHONDONTWRITEBYTECODE="1")
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests), "-q", "--tb=no",
             "-p", "no:cacheprovider"],
            cwd=str(task), env=env, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return None
    def n(pattern):
        m = re.search(pattern, out.stdout)
        return int(m.group(1)) if m else 0
    passed, failed, errors = n(r"(\d+) passed"), n(r"(\d+) failed"), n(r"(\d+) error")
    total = passed + failed + errors
    return passed / total if total else None


def survey(task):
    suite = task / "tests" / "test_outputs.py"
    count = 0
    if suite.exists():
        count = len(set(re.findall(
            r"^def (test_\w+)", suite.read_text(encoding="utf-8", errors="replace"), re.M)))
    note = task / "CRUX.md"
    cruxes = sorted(set(LETTER.findall(
        note.read_text(encoding="utf-8", errors="replace")))) if note.exists() else []
    engine = (task / "solution" / "engine").is_dir()
    return {
        "task": task.name,
        "kind": "engine" if engine else "repo",
        "tests": count,
        "cruxes": cruxes,
        "proof": (task / "tools" / "check_crux.py").exists(),
        "gold": ratio(task, task / "solution" / "engine") if engine else None,
        "stub": ratio(task, task / "environment" / "engine") if engine else None,
    }


def main():
    tasks = sorted(p for p in ROOT.iterdir()
                   if p.is_dir() and (p / "task.toml").exists())
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(survey, tasks))

    def show(v):
        return "  -  " if v is None else "%.3f" % v

    print("%-38s %-6s %5s %6s %6s %-5s %s"
          % ("TASK", "KIND", "TESTS", "GOLD", "STUB", "PROOF", "CRUX"))
    hardened, broken, thin, undone = [], [], [], []
    for r in rows:
        print("%-38s %-6s %5d %6s %6s %-5s %s"
              % (r["task"], r["kind"], r["tests"], show(r["gold"]), show(r["stub"]),
                 "yes" if r["proof"] else " - ", ",".join(r["cruxes"]) or "-"))
        if r["cruxes"] and r["proof"]:
            hardened.append(r["task"])
        else:
            undone.append(r["task"])
        if r["kind"] == "engine" and r["gold"] is not None and r["gold"] < 1.0:
            broken.append("%s gold=%.3f" % (r["task"], r["gold"]))
        if r["stub"]:
            broken.append("%s stub=%.3f" % (r["task"], r["stub"]))
        if r["tests"] < 14:
            thin.append("%s(%d)" % (r["task"], r["tests"]))

    print()
    print("%d tasks: %d hardened, %d still to do" % (len(rows), len(hardened), len(undone)))
    print("BROKEN (gold < 1.0 or stub > 0): %d" % len(broken))
    for b in broken:
        print("   " + b)
    print("thin suites (< 14 tests): %d" % len(thin))
    if thin:
        print("   " + " ".join(thin))
    if undone:
        print("\nnot yet hardened:")
        for i in range(0, len(undone), 3):
            print("   " + "  ".join("%-36s" % u for u in undone[i:i + 3]))
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
