"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_rotation.py over the held-out rosters in /tests/rosters, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
rosters, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "rosters")
REFERENCE = os.path.join(TESTS_DIR, "reference_rotation.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="rotation-verify-")
HELD_OUT = os.path.join(WORK, "rosters")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_rotation  # noqa: E402

REASONS = {"ROTATION", "SUBSTITUTE", "OVERRIDE", "UNCOVERED"}


def _rosters(roster_dir):
    """What each capture configured, so the report can be checked against it."""
    facts = {}
    for name in sorted(os.listdir(roster_dir)):
        if not name.endswith(".roster"):
            continue
        with open(os.path.join(os.path.realpath(roster_dir), name),
                  encoding="utf-8") as handle:
            config = json.loads(handle.readline())
        facts[name[: -len(".roster")]] = {
            "names": [e["name"] for e in config["engineers"]],
            "start": config["start"],
            "days": config["days"],
        }
    return facts


def _expected(roster_dir):
    if os.path.islink(roster_dir):
        raise ValueError("roster_dir cannot be a symlink")
    real_dir = os.path.realpath(roster_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".roster"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("roster %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".roster")]] = reference_rotation.replay_text(
                handle.read())
    return report


EXPECTED = _expected(HELD_OUT)
ROSTERS = _rosters(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(roster_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(roster_dir),
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


def test_tool_runs_on_unseen_rosters():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the four
    documented keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["assignments", "errors", "handoffs", "shifts"], \
            "%s: wrong keys %s" % (name, sorted(got))
        for key in ("assignments", "shifts", "handoffs", "errors"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for day in got["assignments"]:
            assert isinstance(day, dict) and sorted(day) == ["date", "engineer",
                                                             "reason"], \
                "%s: an assignment must have exactly date, engineer and reason" % name
            assert day["engineer"] is None or isinstance(day["engineer"], str), \
                "%s: engineer must be a name or null" % name
            assert day["reason"] in REASONS, \
                "%s: undocumented reason %r" % (name, day["reason"])
        for shift in got["shifts"]:
            assert isinstance(shift, dict) and sorted(shift) == ["days", "engineer"], \
                "%s: a shift must have exactly engineer and days" % name
            assert isinstance(shift["days"], int) and not isinstance(shift["days"], bool), \
                "%s: days is not an integer" % name
        for handoff in got["handoffs"]:
            assert isinstance(handoff, dict) and sorted(handoff) == ["date", "from",
                                                                     "to"], \
                "%s: a handoff must have exactly date, from and to" % name
        for error in got["errors"]:
            assert isinstance(error, dict) and sorted(error) == ["code", "detail"], \
                "%s: an error must have exactly code and detail" % name


def test_assignments_match():
    """Criterion 3: every day of the window, in order, with its engineer and
    the reason they were chosen."""
    _compare("assignments", "the assignments")


def test_shifts_match():
    """Criterion 4: how many days each engineer ends up with, in rotation
    order."""
    _compare("shifts", "the shift counts")


def test_handoffs_match():
    """Criterion 5: every change of assignee, including either side of an
    uncovered day."""
    _compare("handoffs", "the handoffs")


def test_errors_match():
    """Criterion 6: override errors in capture order, then uncovered days in
    date order."""
    _compare("errors", "errors")


def test_report_is_self_consistent():
    """Criterion 7: only rostered engineers, only dates inside the window,
    shift counts that add up, and handoffs that follow the assignments."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        facts = ROSTERS[name]
        dates = [day.get("date") for day in got.get("assignments", [])]
        engineers = [day.get("engineer") for day in got.get("assignments", [])]

        if any(who is not None and who not in facts["names"] for who in engineers):
            wrong.append("%s: an engineer who is not on the roster" % name)
        if len(dates) != facts["days"] or len(set(dates)) != len(dates):
            wrong.append("%s: the window is not covered exactly once" % name)
        if dates and dates[0] != facts["start"]:
            wrong.append("%s: the plan does not begin at the start date" % name)
        if dates != sorted(dates):
            wrong.append("%s: the days are out of order" % name)

        counted = {who: engineers.count(who) for who in facts["names"]}
        reported = {shift.get("engineer"): shift.get("days")
                    for shift in got.get("shifts", [])}
        if any(reported.get(who) != count for who, count in counted.items()):
            wrong.append("%s: the shift counts do not match the plan" % name)

        changes = [{"date": dates[i], "from": engineers[i - 1], "to": engineers[i]}
                   for i in range(1, len(dates)) if engineers[i] != engineers[i - 1]]
        if got.get("handoffs") != changes:
            wrong.append("%s: the handoffs do not follow the assignments" % name)
    assert not wrong, "; ".join(sorted(set(wrong)))


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces
    expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
