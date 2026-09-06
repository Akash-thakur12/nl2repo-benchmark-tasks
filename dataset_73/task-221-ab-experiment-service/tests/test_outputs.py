"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

This task is an open brief: there is no single correct report, so there is
nothing to diff against. Ground truth is instead the set of properties the brief
states, written out in /tests/reference_properties.py and applied here to
whatever the candidate produced for each held-out capture. That module and the
held-out captures are removed from disk before the candidate is invoked, and the
candidate runs from a scratch directory over a copy of the captures.

Nothing here assumes a hash, a bucketing scheme, an evaluation order or a
repository layout. tools/check_variants.py is the evidence for that: it checks
that ten legitimately different implementations pass every one of these tests,
and that sixteen implementations which break the brief each fail at least one.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HELD_OUT_SRC = os.path.join(TESTS_DIR, "captures")
PROPERTIES = os.path.join(TESTS_DIR, "reference_properties.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="experiments-verify-")
HELD_OUT = os.path.join(WORK, "captures")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_properties  # noqa: E402

CAPTURES = {}
for _name in sorted(os.listdir(HELD_OUT)):
    if _name.endswith(".experiments"):
        with open(os.path.join(HELD_OUT, _name), encoding="utf-8") as _handle:
            CAPTURES[_name[: -len(".experiments")]] = _handle.read()

for _leftover in (PROPERTIES, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(capture_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(capture_dir),
                           out_path],
                          cwd=WORK, capture_output=True, timeout=180)
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


def _property(name, label):
    """Every capture whose report breaks the named property."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(CAPTURES), "capture keys differ"
    check = dict(reference_properties.CHECKS)[name]
    wrong = []
    for capture_name, text in CAPTURES.items():
        parsed = reference_properties.read_capture(text)
        complaints = check(parsed, REPORT[capture_name])
        if complaints:
            wrong.append("%s: %s" % (capture_name, complaints[0]))
    assert not wrong, "%s: %s" % (label, "; ".join(sorted(wrong)[:4]))


def test_tool_runs_on_unseen_captures():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_has_the_documented_shape():
    """Criterion 2: one entry per capture, the three documented keys, one
    assignment per request in request order, and only documented reason
    codes."""
    _property("shape", "the report shape")


def test_variants_are_declared_ones():
    """Criterion 3: every variant assigned is one the experiment declares, and
    an assignment with no variant does not call itself ASSIGNED."""
    _property("variants", "the variants assigned")


def test_answers_are_stable_and_the_run_repeats():
    """Criterion 4: the same user and experiment always get the same answer,
    and a second run over the same captures produces an identical report."""
    _property("stability", "assignment stability")
    again, error = _run(HELD_OUT, "held-out-again.json")
    assert again is not None, error
    assert again == REPORT, "a second run over the same captures differed"


def test_experiments_that_are_not_open_assign_nobody():
    """Criterion 5: stopped, draft and zero-traffic experiments assign nobody,
    and one at full traffic with nobody excluded assigns everybody."""
    _property("not_running", "experiments that should assign nobody")


def test_excluded_users_are_excluded():
    """Criterion 6: a user an experiment excludes never receives a variant from
    it."""
    _property("exclusions", "the exclusion lists")


def test_exclusion_groups_do_not_overlap():
    """Criterion 7: no user holds a variant of two experiments in one exclusion
    group."""
    _property("exclusion_groups", "the exclusion groups")


def test_weights_reach_every_variant():
    """Criterion 8: equally weighted variants at full traffic each take at least
    a twentieth of the users, and a variant weighted zero takes nobody."""
    _property("spread", "the spread across variants")


def test_summary_agrees_with_the_assignments():
    """Criterion 9: every declared experiment counted, per declared variant,
    with an unassigned count, all agreeing with the assignments listed."""
    _property("summary", "the summary")


def test_unknown_experiments_are_reported():
    """Criterion 10: a request naming an experiment that does not exist is
    reported as an error and as an unassigned request."""
    _property("unknown", "unknown experiments")
