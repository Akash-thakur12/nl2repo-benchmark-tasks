"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_retention.py over the held-out sweeps in /tests/sweeps, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
sweeps, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "sweeps")
REFERENCE = os.path.join(TESTS_DIR, "reference_retention.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="sweep-verify-")
HELD_OUT = os.path.join(WORK, "sweeps")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_retention  # noqa: E402


def _expected(sweep_dir):
    if os.path.islink(sweep_dir):
        raise ValueError("sweep_dir cannot be a symlink")
    real_dir = os.path.realpath(sweep_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".sweep"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("scenario %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".sweep")]] = reference_retention.sweep_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(sweep_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(sweep_dir), out_path],
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


def test_tool_runs_on_unseen_sweeps():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the six documented
    keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["applied", "blocked", "deleted", "errors",
                               "held", "pending"],             "%s: wrong keys %s" % (name, sorted(got))
        for key in ("deleted", "held", "blocked", "errors"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        assert isinstance(got["applied"], bool), "%s: applied is not a boolean" % name
        assert isinstance(got["pending"], int) and not isinstance(got["pending"], bool),             "%s: pending is not an integer" % name
        for key in ("deleted", "held", "blocked"):
            for entry in got[key]:
                assert isinstance(entry, dict) and sorted(entry) == ["id", "table"],                     "%s: a %s row must have exactly table and id" % (name, key)
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "detail"],                 "%s: an error must have exactly code and detail" % name


def test_deleted_rows_match():
    """Criterion 3: the rows deleted, in sweep order, children before parents."""
    _compare("deleted", "deleted rows")


def test_held_rows_match():
    """Criterion 4: expired rows an active hold protected."""
    _compare("held", "held rows")


def test_blocked_rows_match():
    """Criterion 5: expired, unheld rows that still had a surviving child."""
    _compare("blocked", "blocked rows")


def test_pending_and_applied_match():
    """Criterion 6: how many rows the batch limit held back, and whether the
    sweep was applied."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if (REPORT.get(name, {}).get("pending"),
                 REPORT.get(name, {}).get("applied"))
             != (want["pending"], want["applied"])]
    assert not wrong, "pending or applied differs in: %s" % ", ".join(sorted(wrong))


def test_no_row_appears_twice():
    """Criterion 7: a row is deleted, held or blocked, never more than one."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        seen = []
        for key in ("deleted", "held", "blocked"):
            seen += [(r.get("table"), r.get("id")) for r in got.get(key, [])]
        if len(seen) != len(set(seen)):
            wrong.append(name)
    assert not wrong, "a row is reported more than once in: %s" % ", ".join(sorted(wrong))


def test_errors_match():
    """Criterion 8: tables whose parent does not exist, in the order found."""
    _compare("errors", "errors")


def test_sample_report_is_reproduced():
    """Criterion 9: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
