#!/usr/bin/env python3
"""Mechanical proof that the cruxes bite.

For each crux this builds a copy of the reference repository, applies the
wrong-default patch a competent implementer would plausibly have written,
installs it as if it were the candidate's `/app`, and runs the real behaviour
suite against it. It then asserts two things:

  * the patched repository still reproduces environment/samples/expected.json
    byte for byte, so the visible corpus gives it a green light; and
  * it still fails at least one held-out test, naming which.

The unpatched reference is run first and must pass everything.

No expected values are embedded here: ground truth comes from
tests/reference_rotation.py the same way the suite derives it. This script does
not ship in the task image.
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
REPO = ROOT / "solution" / "repo"
SAMPLES = ROOT / "environment" / "samples"
TESTS = ROOT / "tests"

WINDOWS = os.name == "nt"


# --------------------------------------------------------------- the patches
def patch(app, relative, old, new):
    path = app / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError("%s: patch anchor not found:\n%s" % (relative, old))
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def wrong_raw_clock(app):
    """Crux E: stamp events with the record's own `t`.

    `self.now = record["t"]` is the line every implementer writes. It is
    invisible in every sample, because sample timestamps never go backwards.
    """
    patch(app, "rotator/engine.py",
          'self.now = max(self.now, record["t"])',
          'self.now = record["t"]')


def wrong_current_grace(app):
    """Crux I: measure a running countdown against the policy in force now.

    "the new policy applies from now on" is the obvious reading, and it
    retunes deadlines that were granted under the old window.
    """
    patch(app, "rotator/versions.py",
          "        version, started, window = self._grace\n"
          "        if now - started >= window:",
          "        version, started, _window = self._grace\n"
          "        if now - started >= self.policy:")


def wrong_ignore_policy(app):
    """Crux I, easy half: parse the `policy` record and throw it away."""
    patch(app, "rotator/engine.py",
          "        self.versions.set_policy(record[\"grace_seconds\"])",
          "        return")


def wrong_snapshot_membership(app):
    """Crux H: freeze the cohort when the stage begins.

    'the wave's cohort is fixed when the wave starts' looks like the safer
    engineering choice, and no sample or archived rotation would notice.
    """
    patch(app, "rotator/rollout.py",
          "        self.index = 0\n",
          "        self.index = 0\n        self.cohort = None\n")
    patch(app, "rotator/rollout.py",
          "        self.index += 1",
          "        self.index += 1\n        self.cohort = None")
    patch(app, "rotator/engine.py",
          "            outstanding = [cid for cid in self.fleet.members_of(env)\n"
          "                           if (cid, self.rollout.version) not in self.acks]",
          "            if self.rollout.cohort is None:\n"
          "                self.rollout.cohort = self.fleet.members_of(env)\n"
          "            outstanding = [cid for cid in self.rollout.cohort\n"
          "                           if (cid, self.rollout.version) not in self.acks]")


VARIANTS = [
    ("reference (unpatched)", None),
    ("E: the clock is copied from the record, not clamped", wrong_raw_clock),
    ("I: a policy change retunes a running countdown", wrong_current_grace),
    ("I: the policy record is ignored altogether", wrong_ignore_policy),
    ("H: stage membership is snapshotted when the stage begins",
     wrong_snapshot_membership),
]


# ------------------------------------------------------------------- harness
RUN_CMD = "@echo off\r\nset PYTHONPATH=%~dp0;%PYTHONPATH%\r\npython -m rotator %1 %2\r\n"


def build(workdir, mutate):
    app = workdir / "app"
    shutil.copytree(REPO, app)
    shutil.copytree(SAMPLES, app / "samples")
    if mutate is not None:
        mutate(app)
    os.chmod(app / "run.sh", 0o755)
    tool = app / "run.sh"
    if WINDOWS:                      # a .sh is not executable here
        tool = app / "run.cmd"
        tool.write_text(RUN_CMD, encoding="utf-8", newline="")
    tests = workdir / "tests"
    shutil.copytree(TESTS, tests, ignore=shutil.ignore_patterns("__pycache__"))
    return app, tool, tests


def reproduces_samples(app, tool, workdir):
    out = workdir / "samples.json"
    proc = subprocess.run([str(tool), str(app / "samples"), str(out)],
                          capture_output=True, cwd=str(workdir))
    if proc.returncode != 0:
        return False, "run.sh exited %d" % proc.returncode
    got = json.loads(out.read_text(encoding="utf-8"))
    want = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    return got == want, "" if got == want else "sample report differs"


def run_suite(app, tool, tests, workdir):
    env = dict(os.environ)
    env["APP_DIR"] = str(app)
    env["ROTATE_TOOL"] = str(tool)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests / "test_outputs.py"),
         "-v", "--tb=no", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(workdir), env=env)
    results = re.findall(r"::([\w]+) (PASSED|FAILED|ERROR)\b", proc.stdout)
    if not results:
        raise AssertionError("no tests ran:\n%s\n%s" % (proc.stdout[-3000:],
                                                        proc.stderr[-2000:]))
    passed = [n for n, s in results if s == "PASSED"]
    failed = [n for n, s in results if s != "PASSED"]
    return passed, failed


def main():
    rows = []
    for label, mutate in VARIANTS:
        workdir = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
        try:
            app, tool, tests = build(workdir, mutate)
            same, why = reproduces_samples(app, tool, workdir)
            passed, failed = run_suite(app, tool, tests, workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        rows.append((label, mutate is None, same, why, passed, failed))

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %-9s  %s" % (width, "implementation", "samples",
                                    "suite", "failing tests"))
    print("-" * (width + 40))
    for label, is_ref, same, _why, passed, failed in rows:
        print("%-*s  %-8s  %-9s  %s" % (
            width, label, "pass" if same else "FAIL",
            "%d/%d" % (len(passed), len(passed) + len(failed)),
            ", ".join(failed) if failed else "-"))
    print()

    problems = []
    for label, is_ref, same, why, passed, failed in rows:
        if is_ref:
            if failed:
                problems.append("the reference fails: %s" % ", ".join(failed))
            if not same:
                problems.append("the reference does not reproduce the samples: %s" % why)
            continue
        if not same:
            problems.append("%s is already rejected by the visible samples (%s), "
                            "so it is not a crux" % (label, why))
        if not failed:
            problems.append("%s passes the whole suite - the crux does not bite"
                            % label)
        if not passed:
            problems.append("%s fails everything - reward is not continuous "
                            "across this crux" % label)

    if problems:
        print("PROBLEMS:")
        for line in problems:
            print("  -", line)
        return 1
    print("OK: the reference passes everything; every wrong default reproduces\n"
          "    the visible samples, still fails held-out tests, and still\n"
          "    passes others, so partial understanding scores partially.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
