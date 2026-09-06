"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_supervisor.py over the held-out sessions in /tests/sessions, so
no expected value is hardcoded. Both are removed from disk before the candidate
is invoked, and the candidate runs from a scratch directory over a copy of the
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
REFERENCE = os.path.join(TESTS_DIR, "reference_supervisor.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="supervisor-verify-")
HELD_OUT = os.path.join(WORK, "sessions")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_supervisor  # noqa: E402

EVENT_KINDS = {"crashed", "failed", "restarted", "drained"}
STATES = {"running", "down", "draining", "stopped", "failed"}


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
            raise ValueError("session %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".session")]] = reference_supervisor.replay_text(
                handle.read())
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
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(session_dir),
                           out_path],
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
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the three
    documented keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["errors", "events", "workers"], \
            "%s: wrong keys %s" % (name, sorted(got))
        for key in ("events", "workers", "errors"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for event in got["events"]:
            assert isinstance(event, dict) and sorted(event) == ["kind", "t", "worker"], \
                "%s: an event must have exactly t, worker and kind" % name
        for worker in got["workers"]:
            assert isinstance(worker, dict) and sorted(worker) == [
                "crashes", "name", "restarts", "state"], \
                "%s: a worker must have exactly name, state, restarts and crashes" % name
            for key in ("restarts", "crashes"):
                assert isinstance(worker[key], int) and not isinstance(worker[key], bool), \
                    "%s: %s is not an integer" % (name, key)
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "detail"], \
                "%s: an error must have exactly code and detail" % name


def test_events_match():
    """Criterion 3: every event, in the order it happened, with its time,
    worker and kind."""
    _compare("events", "the event log")


def test_worker_states_match():
    """Criterion 4: each worker's final state, in configuration order."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if [(w["name"], w["state"])
                 for w in REPORT.get(name, {}).get("workers", [])]
             != [(w["name"], w["state"]) for w in want["workers"]]]
    assert not wrong, "final worker states differ in: %s" % ", ".join(sorted(wrong))


def test_restart_and_crash_counts_match():
    """Criterion 5: each worker's restart and crash totals."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if [(w["name"], w["restarts"], w["crashes"])
                 for w in REPORT.get(name, {}).get("workers", [])]
             != [(w["name"], w["restarts"], w["crashes"]) for w in want["workers"]]]
    assert not wrong, "restart or crash counts differ in: %s" % ", ".join(sorted(wrong))


def test_errors_match():
    """Criterion 6: records naming a worker nobody configured, in the order
    they were read."""
    _compare("errors", "errors")


def test_report_is_self_consistent():
    """Criterion 7: only the four documented event kinds and five documented
    states appear, event times never go backwards, and no worker reports more
    restarts than crashes."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        events = got.get("events", [])
        if any(event.get("kind") not in EVENT_KINDS for event in events):
            wrong.append("%s: undocumented event kind" % name)
        times = [event.get("t") for event in events]
        if times != sorted(times):
            wrong.append("%s: events are out of order" % name)
        for worker in got.get("workers", []):
            if worker.get("state") not in STATES:
                wrong.append("%s: undocumented state %r" % (name, worker.get("state")))
            if worker.get("restarts", 0) > worker.get("crashes", 0):
                wrong.append("%s: %s restarts more often than it crashes"
                             % (name, worker.get("name")))
    assert not wrong, "; ".join(sorted(set(wrong)))


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces
    expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
