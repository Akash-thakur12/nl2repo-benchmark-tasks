"""Behaviour tests for /app/run.sh.

The first six tests are the numbered success criteria, compared over the whole
held-out corpus. The rest compare one mechanism at a time over a named subset of
it, so an implementation that gets most of the runner right scores most of the
marks instead of falling off a cliff.

Ground truth is derived here by running the reference model in
/tests/reference_runner.py over the held-out sessions in /tests/sessions, so no
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
REFERENCE = os.path.join(TESTS_DIR, "reference_runner.py")

# Verification always runs against /app. APP_DIR exists only so that the
# repository's own tooling (tools/check_crux.py) can point the same suite at a
# throwaway copy of a deliberately wrong implementation; it is never set on the
# graded path, where this resolves to /app exactly as before.
APP = os.environ.get("APP_DIR", "/app")
GRADED = os.path.realpath(APP) == os.path.realpath("/app")
TOOL = os.path.join(APP, "run.sh")
SAMPLES = os.path.join(APP, "samples")

WORK = tempfile.mkdtemp(prefix="migrate-verify-")
HELD_OUT = os.path.join(WORK, "sessions")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_runner  # noqa: E402


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
            report[name[: -len(".session")]] = reference_runner.replay_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

if GRADED:
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


def _family(names, label):
    """Compare the whole report entry for one named group of captures."""
    assert REPORT is not None, ERROR
    missing = [n for n in names if n not in EXPECTED]
    assert not missing, "held-out corpus is missing: %s" % ", ".join(missing)
    wrong = [n for n in names if REPORT.get(n) != EXPECTED[n]]
    assert not wrong, "%s: wrong in %s" % (label, ", ".join(sorted(wrong)))


# --------------------------------------------------------------------------
# The six numbered success criteria, over the whole corpus.
# --------------------------------------------------------------------------

def test_tool_runs_on_unseen_sessions():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of sessions it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per session, exactly the three
    documented keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "session keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["applied", "errors", "state"],             "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["applied"], list), "%s: applied is not an array" % name
        assert isinstance(got["errors"], list), "%s: errors is not an array" % name
        assert isinstance(got["state"], dict), "%s: state is not an object" % name
        assert sorted(got["state"]) == ["applied", "current", "dirty"],             "%s: state must have exactly current, dirty and applied" % name
        for entry in got["applied"]:
            assert isinstance(entry, dict), "%s: an applied entry is not an object" % name
            assert sorted(entry) in (["direction", "version"], ["direction", "name"]),                 "%s: an applied entry must be version+direction or name+direction" % name
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "command", "version"],                 "%s: an error must have exactly command, code and version" % name


def test_applied_sequence_matches():
    """Criterion 3: every apply, rollback and repeatable run, in order."""
    _compare("applied", "the applied sequence")


def test_errors_match():
    """Criterion 4: one entry per failing command, in command order, with the
    code and version the specification gives it."""
    _compare("errors", "errors")


def test_final_state_matches():
    """Criterion 5: current, dirty and the applied version list."""
    _compare("state", "final state")


def test_sample_report_is_reproduced():
    """Criterion 6: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"


# --------------------------------------------------------------------------
# One mechanism at a time.
# --------------------------------------------------------------------------

def test_versions_are_ordered_numerically():
    """Spec 1.4: versioned migrations are ordered by the integer version, never
    by the text of it, so 10 comes after 9."""
    _family(["h01", "h02", "h03"], "numeric version ordering")


def test_reformatting_is_not_drift():
    """Spec 1.3 with samples/checksums.json: the runner digests the bodies as
    it stores them, so a file whose line endings, trailing spaces or trailing
    blank lines changed - and nothing else - is not drift."""
    _family(["h39", "h40", "h41", "h43", "h44"], "reformatting is not drift")


def test_a_real_edit_is_still_drift():
    """Spec 3.3 with 1.3: leading and interior whitespace, case and content are
    part of the body, so a re-indent or a rewrite is drift like any other
    change."""
    _family(["h04", "h32", "h42"], "a real edit is drift")


def test_drift_names_the_lowest_drifted_version():
    """Spec 3.3: the error names the lowest applied version whose recorded
    checksum and current checksum actually disagree."""
    _family(["h05", "h46"], "drift names the lowest drifted version")


def test_deleted_definitions_are_reported_missing():
    """Spec 3.4: an applied migration with no definition any more is MISSING,
    naming the lowest such version, and the baseline exempts rows under it."""
    _family(["h06", "h11"], "deleted definitions")


def test_preflight_runs_in_order():
    """Spec 3.1-3.5: the checks run lock, dirty, drift, missing, out-of-order
    and stop at the first failure."""
    _family(["h07", "h18", "h36"], "preflight order")


def test_out_of_order_gate():
    """Spec 3.5: a defined, unapplied migration below current is OUT_OF_ORDER
    unless allow_out_of_order is set."""
    _family(["h08", "h09"], "the out-of-order gate")


def test_config_baseline_is_a_floor():
    """Spec 2, 3.4, 4.2, 4.3: versions at or below the baseline from `config`
    are never run or rolled back and are exempt from drift and missing."""
    _family(["h10", "h25", "h35"], "the configured baseline")


def test_baseline_record_moves_the_floor():
    """The `baseline` capture record (session-format.md, spec 2) moves the
    floor mid-session, and every later check uses the floor in force when the
    command runs: it exempts drift and missing under it, stops `down` and `to`
    there, and shrinks both the pending set and the out-of-order window."""
    _family(["h48", "h49", "h51", "h52"], "a baseline record moving the floor")


def test_baseline_record_preserves_history():
    """docs/incident-2025-03-14.md: moving the baseline rewrites nothing.
    Sub-baseline rows stay in state.applied, current is the baseline rather
    than null when nothing above it is applied, and lowering the baseline again
    re-exposes the same rows."""
    _family(["h47", "h50"], "a baseline record preserving history")


def test_targets_move_both_ways():
    """Spec 4.3, 4.4: `to` applies up to and including the target going
    forwards, rolls back everything strictly above it going backwards, treats 0
    as a full rollback to the baseline, and rejects an undefined target."""
    _family(["h20", "h21", "h22", "h23", "h24"], "targets")


def test_step_defaults():
    """Spec 4.1, 4.2: `up` with no steps applies all pending migrations, `down`
    with no steps rolls back exactly one, and asking for more steps than exist
    is not an error."""
    _family(["h33", "h34", "h37"], "step defaults")


def test_failures_and_the_dirty_latch():
    """Spec 5.2-5.5: an irreversible rollback is refused without dirtying the
    runner, a failure stops the command but keeps earlier successes, and only a
    non-transactional failure latches dirty."""
    _family(["h12", "h13", "h14", "h15", "h16"], "failures and the dirty latch")


def test_repeatable_ordering_and_change_detection():
    """Spec 6.1-6.3 with 1.3: repeatables run last, in ascending name order,
    only when their digest changed, never on `down` and never after an error -
    and a repeatable that was reformatted has not changed."""
    _family(["h26", "h27", "h28", "h29", "h30", "h31", "h38", "h45"],
            "repeatable ordering and change detection")


def test_repeatable_failure_has_no_version():
    """Spec 6.4 with docs/runbook.md: a failing repeatable records
    {"command": i, "code": "FAILED", "version": null}, stops the repeatable
    phase, keeps the versioned work applied, latches dirty only when it is not
    transactional, and is retried later because its digest was never
    recorded."""
    _family(["h56", "h57"], "a repeatable failure")


def test_repair_scope():
    """Spec 4.5 with docs/runbook.md: repair reconciles the recorded checksums
    with the catalog and clears dirty without being gated by the preflight, but
    it cannot clear MISSING, must not drop the orphaned row, does not bless a
    changed repeatable, and reconciles rows under the baseline too."""
    _family(["h17", "h19", "h53", "h54", "h55"], "the scope of repair")
