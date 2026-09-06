#!/usr/bin/env python3
"""Prove the three cruxes bite, by running the real test suite against the
wrong-default implementations rather than by asserting that they would fail.

For each wrong default below this script

  1. builds a throwaway candidate repository whose `run.sh` produces that
     wrong reading of the specification,
  2. runs `tests/test_outputs.py` against it, pointed at the candidate instead
     of at `/app`, and
  3. records which test functions failed and what fraction passed.

It then asserts that every wrong default still reproduces
`environment/samples/expected.json` (so the visible corpus cannot rule it out),
that every one of them fails the suite, and that each crux has at least one test
that the corresponding wrong default fails.

The wrong readings themselves are the ones already enumerated in
check_shortcuts.py, so the two tools cannot drift apart. This script does not
ship in the task image and contains no expected values of its own.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(HERE))
import reference_chargeback as ref     # noqa: E402
import check_shortcuts as shortcuts    # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
TESTS = ROOT / "tests"


# The wrong defaults, by crux. The keyword arguments are handed to
# check_shortcuts.make_aggregate, which is the same near-miss model that tool
# checks against the samples.
WRONG_DEFAULTS = [
    ("I", "shared_weights bills the whole period; weight_changes is ignored",
     {"ignore_amendments": True},
     ["test_weight_amendment_applies_from_its_own_day"]),
    ("I", "the last-listed amendment is applied retroactively to the period",
     {"amendment_last_listed": True},
     ["test_weight_amendment_selected_by_day_not_position"]),
    ("I", "the latest-dated amendment is applied retroactively to the period",
     {"amendment_latest_day_retroactive": True},
     ["test_weight_amendment_selected_by_day_not_position"]),
    ("I", "the earlier entry wins when two amendments share a day",
     {"amendment_first_wins_a_shared_day": True},
     ["test_weight_amendment_selected_by_day_not_position"]),
    ("H", "a retired team name is an unknown team (spec 2.3 taken literally)",
     {"ignore_renames": True},
     ["test_retired_name_charges_its_successor"]),
    ("H", "a weight filed under a retired name is struck out (spec 5.5 taken "
          "literally)",
     {"drop_retired_weight": True},
     ["test_retired_weight_folds_into_successor"]),
    ("H", "the remainder tie-break sorts on the weight key as written",
     {"tie_break_on_raw_key": True},
     ["test_remainder_tie_break_uses_the_canonical_name"]),
    ("C", "environment/tools/reconcile_gap.py ported wholesale: the last-listed "
          "amendment bills the month, retired names are unknown teams, and the "
          "amortisation remainder lands on the latest days of the term",
     {"amendment_last_listed": True, "ignore_renames": True,
      "daily": shortcuts.daily_latest_first},
     ["test_weight_amendment_selected_by_day_not_position",
      "test_retired_name_charges_its_successor",
      "test_reservation_amortisation"]),
]


def build_candidate(work, kwargs_source):
    """A repository with the documented command line whose aggregation is the
    wrong default. Nothing here is part of the task; it is a stand-in
    candidate."""
    repo = work / "app"
    repo.mkdir(parents=True)
    shutil.copytree(SAMPLES, repo / "samples")

    (repo / "aggregate.py").write_text(
        "import json, os, sys\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "import check_shortcuts as shortcuts\n"
        "fn = shortcuts.make_aggregate(**%s)\n"
        "export_dir, out_path = sys.argv[1], sys.argv[2]\n"
        "report = {}\n"
        "for name in sorted(os.listdir(export_dir)):\n"
        "    if not name.endswith('.export'):\n"
        "        continue\n"
        "    with open(os.path.join(export_dir, name), encoding='utf-8') as fh:\n"
        "        report[name[:-len('.export')]] = fn(json.load(fh))\n"
        "with open(out_path, 'w', encoding='utf-8') as fh:\n"
        "    json.dump(report, fh, indent=2, sort_keys=True)\n"
        % (str(HERE), str(TESTS), kwargs_source), encoding="utf-8")

    script = repo / "run.sh"
    script.write_text('#!/bin/sh\nset -eu\nDIR="$(cd "$(dirname "$0")" && pwd)"\n'
                      'exec python3 "$DIR/aggregate.py" "$@"\n', encoding="utf-8")
    os.chmod(script, 0o755)

    if os.name == "nt":
        tool = repo / "run.cmd"
        tool.write_text('@%s "%%~dp0aggregate.py" %%*\n' % sys.executable,
                        encoding="utf-8")
    else:
        tool = script
    return repo, tool


def run_suite(work, repo, tool):
    """The real tests/test_outputs.py, pointed at the candidate. The suite
    deletes the reference model and the held-out corpus as it starts, so it runs
    over a copy."""
    suite = work / "tests"
    shutil.copytree(TESTS, suite, ignore=shutil.ignore_patterns("__pycache__"))
    text = (suite / "test_outputs.py").read_text(encoding="utf-8")
    text = text.replace('TOOL = "/app/run.sh"', "TOOL = %r" % str(tool))
    text = text.replace('SAMPLES = "/app/samples"', "SAMPLES = %r" % str(repo / "samples"))
    (suite / "test_outputs.py").write_text(text, encoding="utf-8")

    proc = subprocess.run([sys.executable, "-m", "pytest",
                           str(suite / "test_outputs.py"), "-v", "--tb=no",
                           "-p", "no:cacheprovider"],
                          cwd=str(suite), capture_output=True, text=True)
    results = dict((name, status) for name, status in
                   re.findall(r"::(\w+) (PASSED|FAILED|ERROR)\b", proc.stdout))
    if not results:
        raise SystemExit("could not read pytest output:\n" + proc.stdout[-4000:])
    failed = sorted(n for n, s in results.items() if s != "PASSED")
    return len(results), failed


def reproduces_samples(fn):
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    for path in sorted(SAMPLES.glob("*.export")):
        try:
            if fn(json.loads(path.read_text(encoding="utf-8"))) != expected[path.stem]:
                return False
        except Exception:
            return False
    return True


def main():
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    for path in sorted(SAMPLES.glob("*.export")):
        assert ref.aggregate_text(path.read_text(encoding="utf-8")) == expected[path.stem], \
            "the reference model disagrees with expected.json on %s" % path.stem

    problems = []
    rows = []
    for letter, label, kwargs, must_fail in WRONG_DEFAULTS:
        source = "dict(%s)" % ", ".join(
            "%s=%s" % (k, "shortcuts." + v.__name__ if callable(v) else repr(v))
            for k, v in kwargs.items())
        fn = shortcuts.make_aggregate(**kwargs)

        if not reproduces_samples(fn):
            problems.append("%s: rejected by the visible samples, so it is not a "
                            "wrong default anyone would reach" % label)

        work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
        try:
            repo, tool = build_candidate(work, source)
            total, failed = run_suite(work, repo, tool)
        finally:
            shutil.rmtree(work, ignore_errors=True)

        if not failed:
            problems.append("%s: passes the whole suite - the crux does not bite"
                            % label)
        missing = [name for name in must_fail if name not in failed]
        if missing:
            problems.append("%s: expected to fail %s, but they passed"
                            % (label, ", ".join(missing)))
        rows.append((letter, label, total - len(failed), total, failed))

    for letter, label, passed, total, failed in rows:
        print("crux %s  %s" % (letter, label))
        print("        samples reproduced : yes")
        print("        suite              : %d/%d passed" % (passed, total))
        print("        failing tests      : %s" % ", ".join(failed))
        print()

    print("wrong defaults checked : %d" % len(rows))
    print("all still reproduce environment/samples/expected.json")
    print("all fail the suite; scores range %d/%d to %d/%d"
          % (min(r[2] for r in rows), rows[0][3],
             max(r[2] for r in rows), rows[0][3]))

    if problems:
        print("\nPROBLEMS:")
        for line in problems:
            print("  -", line)
        sys.exit(1)
    print("\nOK: every wrong default survives the visible samples and is caught "
          "by the held-out suite, and each crux has a test that names it.")


if __name__ == "__main__":
    main()
