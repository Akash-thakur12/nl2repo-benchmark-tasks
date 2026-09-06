#!/usr/bin/env python3
"""Mechanical proof that the three cruxes bite.

For each wrong default this script builds a complete, working detector that
takes that default and is otherwise a faithful implementation of the
specification, installs it as a repository with its own run.sh, and runs the
real behaviour suite (tests/test_outputs.py) against it. It then asserts that

  * the wrong-default detector still reproduces environment/samples/expected.json
    exactly - so nothing visible to the candidate rejects it, and
  * the suite still fails, naming which test functions caught it - so the
    held-out corpus does.

A wrong default that failed the samples would be no evidence of difficulty; one
that passed the suite would mean the crux is not tested. Both are errors here.

This script does not ship in the task image. It contains no expected values:
everything is derived from tests/reference_flakiness.py and the corpora.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SAMPLES = ROOT / "environment" / "samples"
DOCS = ROOT / "environment" / "docs"
TESTS = ROOT / "tests"

sys.path.insert(0, str(TESTS))
import reference_flakiness as ref  # noqa: E402


# --------------------------------------------------------------------------
# The wrong-default detector, generated with its flags baked in. Apart from the
# flagged decision it follows docs/flakiness-spec.md exactly.
# --------------------------------------------------------------------------
DETECTOR = '''
import json, os, sys

FLAGS = %(flags)r

PASSED = "passed"
NOT_PASSED = ("failed", "error")
SKIPPED = "skipped"
KNOWN = (PASSED, SKIPPED) + NOT_PASSED
EVIDENCE = frozenset(("completed", "failed", "timed_out"))


def bucket(run):
    if FLAGS.get("raw_commit_string"):
        return run["commit"]
    if FLAGS.get("prefix_without_case_fold"):
        return run["commit"][:7]
    return run["commit"].strip().lower()[:7]


def evidential(run):
    if FLAGS.get("every_run_is_evidence"):
        return True
    return run.get("outcome") in EVIDENCE


def policy(capture):
    if FLAGS.get("policy_from_stamp"):
        return capture["min_commits"], capture["threshold_percent"]
    history = capture["policy_history"]
    if FLAGS.get("policy_newest_revision"):
        rev = max(history, key=lambda r: r["effective_at"])
    else:
        at = capture["captured_at"]
        rev = max((r for r in history if r["effective_at"] <= at),
                  key=lambda r: r["effective_at"])
    return rev["min_commits"], rev["threshold_percent"]


def roster(capture):
    entries = capture.get("quarantined") or []
    if FLAGS.get("roster_ignores_dates"):
        return set(e["test"] for e in entries)
    at = capture["captured_at"]
    names = set()
    for e in entries:
        if e["added_at"] > at:
            continue
        lifted = e.get("lifted_at")
        if lifted is not None and lifted <= at:
            continue
        names.add(e["test"])
    return names


def rank(capture):
    min_commits, threshold = policy(capture)
    quarantined = roster(capture)
    per_test, errors = {}, []
    for run in capture.get("runs", []) or []:
        if not evidential(run):
            continue
        key = bucket(run)
        for result in run.get("results", []) or []:
            status = result["status"]
            if status not in KNOWN:
                errors.append({"code": "UNKNOWN_STATUS", "detail": status})
                continue
            per_test.setdefault(result["test"], {}).setdefault(key, []).append(status)
    rows = []
    for name, commits in per_test.items():
        counted = flaky = 0
        for statuses in commits.values():
            live = [s for s in statuses if s != SKIPPED]
            if not live:
                continue
            counted += 1
            if PASSED in live and any(s in NOT_PASSED for s in live):
                flaky += 1
        if counted == 0:
            continue
        rate = flaky * 100 // counted
        rows.append({"name": name, "commits": counted, "flaky_commits": flaky,
                     "rate": rate,
                     "quarantine": (counted >= min_commits and rate >= threshold)
                                   or name in quarantined})
    rows.sort(key=lambda r: (-r["rate"], -r["commits"], r["name"]))
    return {"tests": rows,
            "recommend": [r["name"] for r in rows if r["quarantine"]],
            "errors": errors}


def main(argv):
    capture_dir, out_path = argv[1], argv[2]
    report = {}
    for name in sorted(os.listdir(capture_dir)):
        if not name.endswith(".capture"):
            continue
        with open(os.path.join(capture_dir, name), encoding="utf-8") as handle:
            report[name[:-len(".capture")]] = rank(json.load(handle))
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''

RUN_SH = ('#!/bin/sh\n'
          'set -eu\n'
          'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
          'exec python3 "$DIR/detector.py" "$@"\n')


WRONG_DEFAULTS = [
    ("E", "groups results by the raw commit string",
     {"raw_commit_string": True}),
    ("E", "compares the 7-character prefix without folding case",
     {"prefix_without_case_fold": True}),
    ("H", "treats every run's results as evidence",
     {"every_run_is_evidence": True}),
    ("I", "reads the policy stamped on the capture",
     {"policy_from_stamp": True}),
    ("I", "takes the newest revision in the policy ledger",
     {"policy_newest_revision": True}),
    ("I", "reads the quarantine roster without its dates",
     {"roster_ignores_dates": True}),
    ("E+H+I", "the retired legacy_triage reading: raw commit string, every run "
              "counted, stamped policy, undated roster",
     {"raw_commit_string": True, "every_run_is_evidence": True,
      "policy_from_stamp": True, "roster_ignores_dates": True}),
]


def build(app_dir, flags):
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "detector.py").write_text(DETECTOR % {"flags": flags},
                                         encoding="utf-8", newline="\n")
    run_sh = app_dir / "run.sh"
    run_sh.write_text(RUN_SH, encoding="utf-8", newline="\n")
    run_sh.chmod(0o755)
    shutil.copytree(DOCS, app_dir / "docs")
    shutil.copytree(SAMPLES, app_dir / "samples")


def suite_copy(work, app_dir):
    """A copy of the real suite with /app repointed at the temporary repo, and
    a bash shim when running on Windows. Nothing else is changed."""
    dest = work / "tests"
    shutil.copytree(TESTS, dest, ignore=shutil.ignore_patterns("__pycache__"))
    path = dest / "test_outputs.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace('TOOL = "/app/run.sh"',
                        'TOOL = %r' % str(app_dir / "run.sh"))
    text = text.replace('SAMPLES = "/app/samples"',
                        'SAMPLES = %r' % str(app_dir / "samples"))
    if os.name == "nt":
        text = text.replace(
            "proc = subprocess.run([os.path.realpath(TOOL), "
            "os.path.realpath(capture_dir), out_path],",
            "cmd = ['bash', os.path.realpath(TOOL), "
            "os.path.realpath(capture_dir), out_path]\n"
            "    proc = subprocess.run(cmd,")
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def reproduces_samples(app_dir, work):
    out = work / "samples.json"
    cmd = [str(app_dir / "run.sh"), str(SAMPLES), str(out)]
    if os.name == "nt":
        cmd = ["bash"] + cmd
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        return False, proc.stderr.decode()[-400:]
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    got = json.loads(out.read_text(encoding="utf-8"))
    return got == expected, ""


def run_suite(test_file, work):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=no",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(work))
    failed, passed = [], []
    for line in proc.stdout.splitlines():
        if "::" not in line:
            continue
        name = line.split("::", 1)[1].split()[0]
        if " FAILED" in line or " ERROR" in line:
            failed.append(name)
        elif " PASSED" in line:
            passed.append(name)
    return passed, failed, proc.stdout


def main():
    # The reference must agree with the shipped expected.json before anything
    # else here means anything.
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    for path in sorted(SAMPLES.glob("*.capture")):
        assert ref.rank_text(path.read_text(encoding="utf-8")) == expected[path.stem], \
            "the reference disagrees with expected.json on %s" % path.stem

    problems = []
    rows = []
    for letter, label, flags in WRONG_DEFAULTS:
        work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
        try:
            app_dir = work / "app"
            build(app_dir, flags)
            ok_samples, why = reproduces_samples(app_dir, work)
            test_file = suite_copy(work, app_dir)
            passed, failed, output = run_suite(test_file, work)
            if not passed and not failed:
                problems.append("%s: %s collected no tests\n%s"
                                % (letter, label, output[-1500:]))
            if not failed:
                problems.append("%s: %s passes the whole suite" % (letter, label))
            if not ok_samples:
                problems.append("%s: %s is already rejected by the samples (%s)"
                                % (letter, label, why))
            rows.append((letter, label, ok_samples, len(passed), failed))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    print("wrong-default detectors, each otherwise a faithful implementation\n")
    for letter, label, ok_samples, n_passed, failed in rows:
        print("crux %s  %s" % (letter, label))
        print("    reproduces samples/expected.json : %s"
              % ("yes" if ok_samples else "NO"))
        print("    behaviour suite                  : %d passed, %d failed"
              % (n_passed, len(failed)))
        for name in failed:
            print("        caught by %s" % name)
        print()

    if problems:
        print("PROBLEMS:")
        for line in problems:
            print("  -", line)
        sys.exit(1)
    print("OK: every wrong default reproduces the visible samples and every one "
          "is caught by the held-out suite.")


if __name__ == "__main__":
    main()
