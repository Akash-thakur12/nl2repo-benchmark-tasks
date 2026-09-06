"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_rotation.py over the held-out sessions in /tests/sessions, so no
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
REFERENCE = os.path.join(TESTS_DIR, "reference_rotation.py")
APP = os.environ.get("APP_DIR", "/app")
TOOL = os.environ.get("ROTATE_TOOL", os.path.join(APP, "run.sh"))
SAMPLES = os.path.join(APP, "samples")

WORK = tempfile.mkdtemp(prefix="rotate-verify-")
HELD_OUT = os.path.join(WORK, "sessions")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_rotation  # noqa: E402


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
            report[name[: -len(".session")]] = reference_rotation.replay_text(handle.read())
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


def _group(names, label):
    """Compare events, errors and state for one named group of captures.

    Groups are per-mechanism so that a partly correct tool scores partly: one
    misread rule costs the tests for that rule, not the whole suite.
    """
    assert REPORT is not None, ERROR
    missing = [n for n in names if n not in EXPECTED]
    assert not missing, "held-out captures missing: %s" % ", ".join(missing)
    wrong = []
    for name in names:
        got = REPORT.get(name)
        want = EXPECTED[name]
        for field in ("events", "errors", "state"):
            if got is None or got.get(field) != want[field]:
                wrong.append("%s.%s" % (name, field))
    assert not wrong, "%s: %s differ from the specification" % (
        label, ", ".join(wrong))


def test_tool_runs_on_unseen_sessions():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of sessions it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per session, exactly the three
    documented keys per entry, with events carrying the fields their kind
    defines."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "session keys differ"
    fields = {
        "plan": ["envs", "kind", "t", "version"],
        "stage": ["env", "kind", "t", "version"],
        "complete": ["env", "kind", "t", "version"],
        "rollback": ["env", "kind", "t", "version"],
        "rotated": ["kind", "t", "version"],
        "revoked": ["kind", "t", "version"],
    }
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["errors", "events", "state"],             "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["events"], list), "%s: events is not an array" % name
        assert isinstance(got["errors"], list), "%s: errors is not an array" % name
        assert sorted(got["state"]) == ["current", "live"],             "%s: state must have exactly current and live" % name
        assert isinstance(got["state"]["live"], list), "%s: live is not an array" % name
        for event in got["events"]:
            assert isinstance(event, dict), "%s: an event is not an object" % name
            kind = event.get("kind")
            assert kind in fields, "%s: unknown event kind %r" % (name, kind)
            assert sorted(event) == fields[kind],                 "%s: a %s event must have exactly %s" % (name, kind, fields[kind])
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "detail"],                 "%s: an error must have exactly code and detail" % name


def test_event_sequence_matches():
    """Criterion 3: every stage, completion, rotation, rollback and revocation,
    in the order it happened."""
    _compare("events", "the event sequence")


def test_errors_match():
    """Criterion 4: refused commands, in record order, with the documented code
    and detail."""
    _compare("errors", "errors")


def test_final_state_matches():
    """Criterion 5: the current version and every version still live."""
    _compare("state", "final state")


def test_sample_report_is_reproduced():
    """Criterion 6: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"


# --------------------------------------------------------------------------
# Per-mechanism groups. Each names one rule of the specification and compares
# all three report fields for the captures that exercise it.
# --------------------------------------------------------------------------


def test_multi_environment_rollout_order():
    """Spec 2.1, 6.2: environments stage in the configured rollout order, and
    a stage waits for every consumer registered in it."""
    _group(["h01", "h04"], "multi-environment rollout")


def test_empty_environment_completes_at_once():
    """Spec 6.1: an environment with no consumers completes as soon as it is
    healthy, rather than waiting for an acknowledgement that never comes."""
    _group(["h02", "h03"], "empty environments")


def test_early_acknowledgements_count():
    """Spec 5.2, 5.3: an acknowledgement is remembered whenever it arrives,
    including before its environment stages and before the version exists."""
    _group(["h05", "h06", "h21", "h24"], "early acknowledgements")


def test_refusals_and_unknown_names():
    """Spec 2.3, 2.4, 4.2, 5.1: unknown environments, unknown consumers and a
    rotation refused while one is in flight."""
    _group(["h07", "h13"], "refusals")


def test_rollback_order():
    """Spec 7.1: an unhealthy staging environment rolls the rotation back, and
    the rollback events are written in the runner's order."""
    _group(["h08", "h09", "h28"], "rollback order")


def test_rollback_discards_version_and_acks():
    """Spec 3.2, 7.2, 7.3: a rolled-back version is discarded with its
    acknowledgements, starts no grace period, and its number is not reused."""
    _group(["h10", "h11", "h12", "h25"], "rollback aftermath")


def test_dry_run_changes_nothing():
    """Spec 4.1: a dry run records a plan and changes nothing at all, in flight
    or not."""
    _group(["h14", "h15", "h16"], "dry runs")


def test_grace_boundary():
    """Spec 8.1, 8.2: a version is revoked on the boundary second and drops out
    of the live set when it is."""
    _group(["h17", "h18"], "the grace boundary")


def test_grace_cut_short_by_new_rotation():
    """Spec 8.3: a version still in its grace period when a new rotation
    completes is revoked at that moment."""
    _group(["h19", "h20", "h22", "h23"], "grace cut short")


def test_clock_never_runs_backwards():
    """Spec 1 and the capture format: a record carrying a `t` behind the record
    before it does not rewind the runner's clock, and events are stamped with
    the clock rather than with the record's own `t`."""
    _group(["h26", "h28"], "the replay clock")


def test_clock_clamp_across_a_grace_deadline():
    """Spec 1, 8.1: a rewound record must not move a grace period's start, so
    it can neither expire nor un-expire a deadline."""
    _group(["h27"], "the replay clock across a grace deadline")


def test_policy_record_is_applied():
    """Spec 8.0: a `policy` record sets the fleet's grace window, and a grace
    period beginning after it serves the new window."""
    _group(["h31"], "a policy change before any grant")


def test_policy_does_not_retune_a_running_countdown():
    """Spec 8.0, 8.1: a grace period serves the window in force when it began;
    a later policy change does not recompute its deadline."""
    _group(["h29", "h30"], "a policy change during a countdown")


def test_late_registration_blocks_a_stage():
    """Spec 6.1: stage membership is read live, so a consumer registered while
    its environment is staging must acknowledge before that stage completes."""
    _group(["h32"], "late registration")


def test_membership_change_completes_a_stage():
    """Spec 2.2, 6.1: moving a consumer out of the staging environment changes
    who the stage is waiting for, and can complete or empty it."""
    _group(["h33", "h34"], "membership leaving a stage")
