"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_scaffolder.py over the held-out plans in /tests/plans, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
plans, so it cannot read the answers out of /tests at verify time.

The candidate is exercised only through its documented command line. Nothing
here imports its code, so the repository may be laid out however its author
likes.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HELD_OUT_SRC = os.path.join(TESTS_DIR, "plans")
REFERENCE = os.path.join(TESTS_DIR, "reference_scaffolder.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="scaffold-verify-")
HELD_OUT = os.path.join(WORK, "plans")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_scaffolder  # noqa: E402


def _expected(plan_dir):
    if os.path.islink(plan_dir):
        raise ValueError("plan_dir cannot be a symlink")
    real_dir = os.path.realpath(plan_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".plan"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("scenario %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".plan")]] = reference_scaffolder.render_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(plan_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(plan_dir), out_path],
                          cwd=WORK, capture_output=True, timeout=120)
    if proc.returncode != 0:
        return None, "exit %d: %s" % (proc.returncode, proc.stderr.decode()[-2000:])
    if not os.path.exists(out_path):
        return None, "the tool wrote no report to %s" % out_path
    if os.path.islink(out_path):
        return None, "output path %s must not be a symlink" % out_path
    with open(os.path.realpath(out_path), encoding="utf-8") as handle:
        try:
            return json.load(handle), ""
        except ValueError as exc:
            return None, "report is not valid JSON: %s" % exc


REPORT, ERROR = (None, "%s is missing" % TOOL)
if os.path.exists(TOOL):
    REPORT, ERROR = _run(HELD_OUT, "held-out.json")



def _compare(field, label):
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if REPORT.get(name, {}).get(field) != want[field]]
    assert not wrong, "%s differs from the specification in: %s" % (
        label, ", ".join(sorted(wrong)))


def test_tool_runs_on_unseen_plans():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of plans it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per plan, exactly the four documented
    keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "plan keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["errors", "files", "hooks", "skipped"],             "%s: wrong keys %s" % (name, sorted(got))
        for key in ("errors", "files", "hooks", "skipped"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for entry in got["files"]:
            assert isinstance(entry, dict) and sorted(entry) == ["content", "mode", "path"],                 "%s: a written file must have exactly path, content and mode" % name
            assert entry["mode"] in ("644", "755"), "%s: bad mode %r" % (name, entry["mode"])
        for entry in got["skipped"]:
            assert isinstance(entry, dict) and sorted(entry) == ["path", "reason"],                 "%s: a skipped file must have exactly path and reason" % name
            assert entry["reason"] in ("EXISTS", "COLLISION"),                 "%s: bad skip reason %r" % (name, entry["reason"])
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "detail"],                 "%s: an error must have exactly code and detail" % name
        for entry in got["hooks"]:
            assert isinstance(entry, str), "%s: a hook must be a string" % name


def test_written_files_match():
    """Criterion 3: every file written, in write order, with the rendered path,
    the rendered content and the right mode."""
    _compare("files", "written files")


def test_skipped_files_match():
    """Criterion 4: every file not written, in declaration order, with the
    reason the specification gives it."""
    _compare("skipped", "skipped files")


def test_hooks_match():
    """Criterion 5: the hooks that ran, in order, rendered."""
    _compare("hooks", "hooks")


def test_errors_match():
    """Criterion 6: the errors produced, with code and detail."""
    _compare("errors", "errors")


def test_sample_report_is_reproduced():
    """Criterion 7: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
