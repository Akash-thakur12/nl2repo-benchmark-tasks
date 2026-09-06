"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_backfill.py over the held-out sessions in /tests/sessions, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
sessions, so it cannot read the answers out of /tests at verify time.

The held-out corpus is grouped into families so that reward stays continuous:
a replay that handles plain single-process captures correctly and nothing else
still scores, and understanding one mechanism at a time adds to that score
rather than being masked by the rest.

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
REFERENCE = os.path.join(TESTS_DIR, "reference_backfill.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"
INCIDENTS = "/app/incidents"

WORK = tempfile.mkdtemp(prefix="backfill-verify-")
HELD_OUT = os.path.join(WORK, "sessions")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_backfill  # noqa: E402


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
            report[name[: -len(".session")]] = reference_backfill.replay_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


# --------------------------------------------------------------- families
def _named(*names):
    return [n for n in names if n in EXPECTED]


def _prefixed(prefix):
    return sorted(n for n in EXPECTED if n.startswith(prefix))


# Single-process captures: chunking, the short final chunk, a resume point, an
# empty range, a floored percentage. Nothing here needs any of the mechanisms
# the samples do not show.
PLAIN = _named("h01", "h02", "h03", "h04", "h05", "h06", "h07", "h08", "h09",
               "h10", "h25", "h26", "h27", "h28")
FAILURE = _named("h11", "h12", "h13", "h14", "h15", "h16", "h17", "h29")
WINDOW = _named("h18", "h19", "h20", "h21", "h22", "h30")
PAUSE = _named("h23", "h24")
BOOTED = _prefixed("b")          # stitched across process restarts
RETUNED = _prefixed("p")         # a control-table edit mid-job
LAGGING = _prefixed("c")         # a boot whose reported checkpoint is stale


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


def _compare(field, label, names=None):
    assert REPORT is not None, ERROR
    chosen = EXPECTED if names is None else {n: EXPECTED[n] for n in names}
    assert chosen, "no sessions in this family"
    wrong = [name for name, want in chosen.items()
             if REPORT.get(name, {}).get(field) != want[field]]
    assert not wrong, "%s differs from the specification in: %s" % (
        label, ", ".join(sorted(wrong)))


# ------------------------------------------------------- criteria 1, 2, 6, 7
def test_tool_runs_on_unseen_sessions():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of sessions it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per session, exactly the three
    documented keys per entry, with each attempt carrying its four fields."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "session keys differ"
    state_fields = ["checkpoint", "done", "halted", "paused", "percent", "total"]
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["attempts", "state", "waits"], \
            "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["attempts"], list), "%s: attempts is not an array" % name
        assert isinstance(got["waits"], int) and not isinstance(got["waits"], bool), \
            "%s: waits is not an integer" % name
        assert sorted(got["state"]) == state_fields, \
            "%s: state must have exactly %s" % (name, state_fields)
        for flag in ("halted", "paused"):
            assert isinstance(got["state"][flag], bool), \
                "%s: %s is not a boolean" % (name, flag)
        for number in ("checkpoint", "done", "total", "percent"):
            value = got["state"][number]
            assert isinstance(value, int) and not isinstance(value, bool), \
                "%s: %s is not an integer" % (name, number)
        for entry in got["attempts"]:
            assert isinstance(entry, dict) and sorted(entry) == ["from", "outcome", "t", "to"], \
                "%s: an attempt must have exactly t, from, to and outcome" % name
            assert entry["outcome"] in ("ok", "fail"), \
                "%s: bad outcome %r" % (name, entry["outcome"])
            assert entry["from"] <= entry["to"], \
                "%s: an attempt covers a backwards range" % name


def test_progress_reconciles():
    """Criterion 6: done is the distance from the start to the checkpoint, and
    percent is that share of the total, floored."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        state = REPORT.get(name, {}).get("state", {})
        if not state:
            wrong.append(name)
            continue
        total, done = state["total"], state["done"]
        expected_percent = 100 if total == 0 else done * 100 // total
        if state["percent"] != expected_percent:
            wrong.append(name)
    assert not wrong, "progress does not reconcile in: %s" % ", ".join(sorted(wrong))


def test_sample_report_is_reproduced():
    """Criterion 7: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"


# ------------------------------------- criteria 3-5, single-process captures
def test_attempts_plain_captures():
    """Criterion 3, single-process captures: chunking in ascending order, the
    short final chunk, and a resume point clamped into the range."""
    _compare("attempts", "the attempt sequence on plain captures", PLAIN)


def test_state_plain_captures():
    """Criterion 4, single-process captures: the checkpoint, the floored
    percentage and the empty range."""
    _compare("state", "final state on plain captures", PLAIN)


def test_waits_plain_captures():
    """Criterion 5, single-process captures: nothing here is rate-limited, so
    nothing here waits."""
    _compare("waits", "the wait count on plain captures", PLAIN)


# --------------------------------------------- criteria 3-4, failures and halts
def test_attempts_failure_captures():
    """Criterion 3, failures: a failed chunk is retried from the same
    checkpoint, and no chunk is attempted after the job halts."""
    _compare("attempts", "the attempt sequence on failure captures", FAILURE)


def test_state_failure_captures():
    """Criterion 4, failures: the checkpoint does not move on a failure, the
    failure count is per chunk, and a halt survives a resume."""
    _compare("state", "final state on failure captures", FAILURE)


# ------------------------------------------- criteria 3, 5, the sliding window
def test_attempts_window_captures():
    """Criterion 3, rate limiting: a rate-limited chunk is retried rather than
    skipped, and every attempt including a failed one counts against the
    window."""
    _compare("attempts", "the attempt sequence on rate-limited captures", WINDOW)


def test_waits_window_captures():
    """Criterion 5, rate limiting: a wait is counted each time the window
    turns an attempt away, at a strictly-less-than boundary."""
    _compare("waits", "the wait count on rate-limited captures", WINDOW)


# ------------------------------------------------------ criterion 4, pausing
def test_state_pause_captures():
    """Criterion 4, pausing: a pause stops attempts without moving the
    checkpoint or clearing the failure count."""
    _compare("state", "final state on paused captures", PAUSE)


# ------------------------- criteria 3-5, captures stitched across restarts
def test_attempts_across_process_restarts():
    """Criterion 3, stitched captures: a capture spans several runner
    processes, each stamping its own clock, and every attempt is reported on
    the timeline that spans the file."""
    _compare("attempts", "the attempt sequence across process restarts", BOOTED)


def test_state_across_process_restarts():
    """Criterion 4, stitched captures: what a restart carries over and what it
    does not, including whether a job that keeps crashing ever halts."""
    _compare("state", "final state across process restarts", BOOTED)


def test_waits_across_process_restarts():
    """Criterion 5, stitched captures: the rate window is not the runner's to
    reset, so it spans a restart."""
    _compare("waits", "the wait count across process restarts", BOOTED)


# --------------------------- criteria 3-4, control-table retunes mid-capture
def test_attempts_after_policy_change():
    """Criterion 3, retunes: a `policy` record changes the configuration from
    that point in the log, and the ranges attempted afterwards show which
    chunk it did and did not reach."""
    _compare("attempts", "the attempt sequence after a retune", RETUNED)


def test_state_after_policy_change():
    """Criterion 4, retunes: a retune moves neither the checkpoint nor the
    plan."""
    _compare("state", "final state after a retune", RETUNED)


# ----------------------- criteria 3-4, a boot whose reported checkpoint lags
def test_checkpoint_never_regresses_across_a_boot():
    """Criteria 3 and 4, reported checkpoints: `cp` comes from the monitoring
    sidecar's read of the job row, and the replay must end at a checkpoint
    consistent with every attempt it reports."""
    _compare("attempts", "the attempt sequence after a reported checkpoint", LAGGING)
    _compare("state", "final state after a reported checkpoint", LAGGING)


# ----------------------------------------------------------- criterion 8
def test_incident_capture_matches_the_gateway_log():
    """Criterion 8: replaying /app/incidents reproduces the gateway's own
    attempt log for INC-4712 - the same ranges, at the same wall-seconds, with
    the same outcomes, the same throttle count and the same final
    checkpoint."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(INCIDENTS, "incidents.json")
    assert report is not None, error
    with open(os.path.join(INCIDENTS, "inc-4712-attempts.json"), encoding="utf-8") as handle:
        gateway = json.load(handle)
    got = report.get("inc-4712")
    assert got is not None, "no entry for inc-4712 in the report"
    assert got["attempts"] == gateway["attempts"], \
        "the replayed attempts disagree with the gateway's log"
    assert got["waits"] == gateway["throttle_events"], \
        "the replayed wait count disagrees with the gateway's throttle count"
    assert got["state"]["checkpoint"] == gateway["final_checkpoint"], \
        "the replay ends at a different checkpoint from the one recorded"
    assert got["state"]["halted"] == gateway["halted"], \
        "the replay disagrees about whether the job halted"


# -------------------------------------- criteria 3-5 over the whole corpus
def test_attempt_sequence_matches():
    """Criterion 3: every attempt, in order, with the key range it covered and
    the time it was made, over every held-out capture."""
    _compare("attempts", "the attempt sequence")


def test_final_state_matches():
    """Criterion 4: checkpoint, progress, and the halted and paused flags,
    over every held-out capture."""
    _compare("state", "final state")


def test_wait_count_matches():
    """Criterion 5: how often the rate limit turned an attempt away, over
    every held-out capture."""
    _compare("waits", "the wait count")
