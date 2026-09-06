"""Behaviour tests for /app/run.sh, one test per specification criterion.

Ground truth is derived here by running the reference model in
/tests/reference_audit.py over the held-out captures in /tests/captures, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
captures, so it cannot read the answers out of /tests at verify time.

The candidate is exercised only through its documented command line. Nothing
here imports its code, so the repository may be laid out however its author
likes.

The corpus-wide comparisons (accepted / duplicates / impossible / errors) are
kept, and the mechanism tests below each assert over a named handful of captures
so that a partially correct exporter scores partially.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HELD_OUT_SRC = os.path.join(TESTS_DIR, "captures")
REFERENCE = os.path.join(TESTS_DIR, "reference_audit.py")
APP = os.environ.get("APP_DIR", "/app")
TOOL = os.path.join(APP, "run.sh")
SAMPLES = os.path.join(APP, "samples")
PRIOR_QUARTER = os.path.join(SAMPLES, "2029Q1")

WORK = tempfile.mkdtemp(prefix="audit-verify-")
HELD_OUT = os.path.join(WORK, "captures")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_audit  # noqa: E402


def _expected(capture_dir):
    if os.path.islink(capture_dir):
        raise ValueError("capture_dir cannot be a symlink")
    real_dir = os.path.realpath(capture_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".capture"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("scenario %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".capture")]] = reference_audit.export_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
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
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(capture_dir), out_path],
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


def _subset(names, fields=("accepted", "duplicates", "impossible", "errors")):
    """Assert the report matches the specification on a named handful."""
    assert REPORT is not None, ERROR
    problems = []
    for name in names:
        want = EXPECTED[name]
        got = REPORT.get(name)
        if not isinstance(got, dict):
            problems.append("%s: no entry in the report" % name)
            continue
        for field in fields:
            if got.get(field) != want[field]:
                problems.append("%s: %s is %s, the specification gives %s" % (
                    name, field, json.dumps(got.get(field)), json.dumps(want[field])))
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------- the contract
def test_tool_runs_on_unseen_captures():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the four documented
    keys per entry, with each flagged sign-in carrying its six fields."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    flagged_fields = ["from", "id", "km", "seconds", "to", "user"]
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["accepted", "duplicates", "errors", "impossible"], (
            "%s: wrong keys %s" % (name, sorted(got)))
        for key in ("accepted", "duplicates", "errors", "impossible"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for entry in got["accepted"] + got["duplicates"]:
            assert isinstance(entry, str), "%s: an id must be a string" % name
        for entry in got["impossible"]:
            assert isinstance(entry, dict) and sorted(entry) == flagged_fields, (
                "%s: a flagged sign-in must have exactly %s" % (name, flagged_fields))
            for field in ("km", "seconds"):
                assert isinstance(entry[field], int) and not isinstance(entry[field], bool), (
                    "%s: %s is not an integer" % (name, field))
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "detail"], (
                "%s: an error must have exactly code and detail" % name)


def test_accepted_events_match():
    """Criterion 3: the ids that survived, in consideration order."""
    _compare("accepted", "accepted events")


def test_duplicates_match():
    """Criterion 4: repeats of a session inside the window, in consideration
    order."""
    _compare("duplicates", "duplicates")


def test_impossible_travel_matches():
    """Criterion 5: every flagged sign-in, with the distance and gap the
    specification computes."""
    _compare("impossible", "impossible travel")


def test_errors_match():
    """Criterion 6: unknown locations, in consideration order."""
    _compare("errors", "errors")


def test_sample_report_is_reproduced():
    """Criterion 7: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"


def test_prior_quarter_export_is_reproduced():
    """Criterion 8: running the tool on /app/samples/2029Q1 reproduces the
    report Security signed off on."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(PRIOR_QUARTER, "q1.json")
    assert report is not None, error
    with open(os.path.join(PRIOR_QUARTER, "q1-signed-off.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), (
            "the export does not reproduce last quarter's signed-off report")


# ------------------------------------------------------------------- ordering
def test_events_are_ordered_by_time():
    """1.1, 1.2: events are considered in ascending t whatever order the log was
    written in, and never in id order."""
    _subset(["h01", "h30", "h31"])


def test_timestamp_ties_break_on_the_id():
    """1.1: two events sharing a t are considered in ascending id."""
    _subset(["h02", "h03"])


# ----------------------------------------------------------------- duplicates
def test_dedup_window_is_inclusive_at_its_boundary():
    """3.2: a repeat at exactly dedup_window_seconds is a duplicate; one a
    second later is accepted."""
    _subset(["h04", "h05"])


def test_an_accepted_repeat_becomes_the_new_baseline():
    """3.3: a session event outside the window is accepted and later events are
    measured against it, not against the session's first event."""
    _subset(["h06"])


def test_duplicates_are_judged_per_user_and_session():
    """3.1: the identity is the pair, so two sessions of one user and one
    session name shared by two users are all distinct."""
    _subset(["h07"])


def test_a_duplicate_never_establishes_a_location():
    """3.4: a suppressed duplicate is not where the user is, and is itself never
    flagged."""
    _subset(["h08", "h25"])


# --------------------------------------------------------------- unknown sites
def test_unknown_locations_are_reported_and_discarded():
    """2.3: an event naming an undefined location produces UNKNOWN_LOCATION and
    takes no further part, including as a previous location."""
    _subset(["h09", "h10", "h26"])


# -------------------------------------------------------------------- failures
def test_a_failure_neither_sets_nor_uses_a_location():
    """4.1: a failed sign-in is accepted and exported but is invisible to the
    travel check on both sides."""
    _subset(["h11", "h12", "h27"])


# --------------------------------------------------------- the arithmetic itself
def test_the_speed_test_is_strict_at_the_limit():
    """4.3: a journey exactly at the limit is not impossible; one second faster
    is."""
    _subset(["h13", "h14"])


def test_a_zero_second_gap_covering_ground_is_impossible():
    """4.3: distance covered in no time at all is flagged, with seconds 0, while
    standing still across a zero gap is not."""
    _subset(["h15", "h16"])


def test_standing_still_is_never_impossible():
    """4.3: a zero distance never exceeds any limit, however tight."""
    _subset(["h21"])


def test_the_distance_is_a_floored_whole_number():
    """2.2: a 14.76 km hop is 14 km, which is neither the rounded nor the
    rounded-up value, and the reported km must say so."""
    _subset(["h19", "h20"])


# ------------------------------------------------------------------ the history
def test_a_flagged_signin_still_becomes_the_previous_location():
    """4.2, 4.4: the flag goes on the later event and that event is still where
    the user now is."""
    _subset(["h17", "h18"])


def test_users_are_independent_of_one_another():
    """4.2: a user is only ever compared against their own previous sign-in."""
    _subset(["h22", "h23"])


def test_a_mixed_capture_is_handled_end_to_end():
    """1-5 together: several users, unsorted, with duplicates, an unknown site,
    a failure and several hops."""
    _subset(["h24", "h29"])


def test_an_empty_capture_produces_four_empty_lists():
    """5.1-5.4: a capture with no events is still a report."""
    _subset(["h28"])


# --------------------------------------------- coordinates in force at the time
def test_distance_uses_the_coordinates_in_force_at_each_event():
    """2.1 and the registry: each leg of a journey uses the coordinates the site
    had at that leg's own time, so a site that moved after a sign-in does not
    turn it into an alert, and the reported km is the as-of distance."""
    _subset(["h32", "h33"])


def test_revisions_are_not_in_chronological_order():
    """The registry: entries appear in filing order, so neither the first nor
    the last element of a revision list is necessarily the one in force."""
    _subset(["h34"])


def test_an_event_before_the_first_revision_uses_the_first_revision():
    """The registry: the oldest revision was backfilled and reaches back to the
    start of the log; no site is ever without coordinates."""
    _subset(["h35"])


# ---------------------------------------------- the policy in force at the time
def test_the_travel_policy_governs_when_present():
    """The registry: where a capture carries a speed_policy the policy is the
    limit, not the flat max_speed_kmh left beside it."""
    _subset(["h36"])


def test_the_policy_is_inclusive_at_its_from_t():
    """The registry: a policy entry is in force for a sign-in at exactly its
    from_t."""
    _subset(["h37"])


def test_the_policy_is_resolved_at_the_later_signin():
    """The registry: the limit applied is the one in force for the sign-in under
    review, which is the later of the two being compared."""
    _subset(["h38"])


def test_a_relocation_and_a_policy_change_together():
    """2.1, 4.3 and the registry: resolving only one of the two as of the event
    time still gives the wrong answer."""
    _subset(["h39"])
