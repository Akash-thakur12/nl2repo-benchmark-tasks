"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_shipper.py over the held-out captures in /tests/sessions, so no
expected value is hardcoded. Both are removed from disk before the candidate
tool is invoked, so the tool cannot read the answers out of /tests at verify
time, and the tool is run from a scratch directory over a copy of the captures.

The tool is only ever exercised through its documented command line. Nothing
here imports the candidate's code, so the repository may be laid out and written
however its author likes.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HELD_OUT_SRC = os.path.join(TESTS_DIR, "sessions")
REFERENCE = os.path.join(TESTS_DIR, "reference_shipper.py")
# The image installs the candidate repository at /app. SHIPPER_APP_DIR only
# exists so the task's own tooling can exercise this suite outside the image;
# the verifier never sets it.
APP = os.environ.get("SHIPPER_APP_DIR", "/app")
TOOL = os.path.join(APP, "run.sh")
SAMPLES = os.path.join(APP, "samples")
# On a POSIX image run.sh is executed directly; Windows has no shebang support.
LAUNCH = [] if os.name != "nt" else ["bash"]

WORK = tempfile.mkdtemp(prefix="shipper-verify-")
HELD_OUT = os.path.join(WORK, "captures")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_shipper  # noqa: E402


def _expected(session_dir):
    if os.path.islink(session_dir):
        raise ValueError("session_dir cannot be a symlink")
    real_dir = os.path.realpath(session_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".session"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("capture %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".session")]] = reference_shipper.replay_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(session_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run(LAUNCH + [os.path.realpath(TOOL), os.path.realpath(session_dir), out_path],
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


def _compare(field):
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if REPORT.get(name, {}).get(field) != want[field]]
    assert not wrong, "%s differs from the specified behaviour in: %s" % (
        field, ", ".join(sorted(wrong)))


def test_tool_runs_on_unseen_captures():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the five documented
    keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    for name, want in EXPECTED.items():
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["delivered", "dlq", "dropped", "offsets", "pending"], \
            "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["delivered"], list), "%s: delivered is not an array" % name
        assert isinstance(got["dlq"], list), "%s: dlq is not an array" % name
        assert isinstance(got["dropped"], int) and not isinstance(got["dropped"], bool), \
            "%s: dropped is not an integer" % name
        assert isinstance(got["pending"], list), "%s: pending is not an array" % name
        assert isinstance(got["offsets"], dict), "%s: offsets is not an object" % name
        for batch in got["delivered"]:
            assert isinstance(batch, dict) and sorted(batch) == ["id", "lines"], \
                "%s: delivered entry must have exactly id and lines" % name
        for fname, view in got["offsets"].items():
            assert sorted(view) == ["acked", "read"], \
                "%s/%s: offsets entry must have exactly read and acked" % (name, fname)


def test_delivered_batches_match_specification():
    """Criterion 3: the same batches, ids and lines, in response order."""
    _compare("delivered")


def test_dead_letters_match_specification():
    """Criterion 4: dead-lettered lines, in order."""
    _compare("dlq")


def test_dropped_count_matches_specification():
    """Criterion 5: the count of lines shed by backpressure."""
    _compare("dropped")


def test_pending_buffer_matches_specification():
    """Criterion 6: what is still buffered when the session ends, in buffer order."""
    _compare("pending")


def test_offsets_match_specification():
    """Criterion 7: final read and acked offsets for every file in the capture."""
    _compare("offsets")


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
