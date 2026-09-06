"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_relay.py over the held-out sessions in /tests/sessions, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
sessions, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "sessions")
REFERENCE = os.path.join(TESTS_DIR, "reference_relay.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="relay-verify-")
HELD_OUT = os.path.join(WORK, "sessions")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_relay  # noqa: E402


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
            raise ValueError("scenario %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".session")]] = reference_relay.replay_text(handle.read())
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
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(session_dir), out_path],
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


def test_tool_runs_on_unseen_sessions():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of sessions it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per session, exactly the five documented
    keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "session keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["accepted", "attempts", "completed", "dlq", "rejected"],             "%s: wrong keys %s" % (name, sorted(got))
        for key in ("accepted", "attempts", "completed", "dlq", "rejected"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for entry in got["rejected"]:
            assert isinstance(entry, dict) and sorted(entry) == ["event_id", "reason"],                 "%s: a rejection must have exactly event_id and reason" % name
        for entry in got["attempts"]:
            assert isinstance(entry, dict) and sorted(entry) ==                 ["at", "attempt", "delivery", "event_id", "subscriber"],                 "%s: an attempt must have exactly delivery, subscriber, event_id, attempt and at" % name
        for entry in got["dlq"]:
            assert isinstance(entry, dict) and sorted(entry) ==                 ["delivery", "event_id", "reason", "subscriber"],                 "%s: a dead letter must have exactly delivery, subscriber, event_id and reason" % name


def test_accepted_events_match():
    """Criterion 3: the event ids admitted, in arrival order."""
    _compare("accepted", "accepted events")


def test_rejections_match():
    """Criterion 4: every rejected webhook, in arrival order, with the reason the
    specification gives it."""
    _compare("rejected", "rejections")


def test_delivery_attempts_match():
    """Criterion 5: every attempt including retries, in dispatch order, with the
    right delivery, subscriber, attempt number and dispatch time."""
    _compare("attempts", "delivery attempts")


def test_completed_deliveries_match():
    """Criterion 6: deliveries answered 200, in response order."""
    _compare("completed", "completed deliveries")


def test_dead_letters_match():
    """Criterion 7: dead-lettered deliveries, in order, with the right reason."""
    _compare("dlq", "dead letters")


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
