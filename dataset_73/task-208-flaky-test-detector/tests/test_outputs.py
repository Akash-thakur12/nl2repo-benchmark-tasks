"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_flakiness.py over the held-out captures in /tests/captures, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
captures, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "captures")
REFERENCE = os.path.join(TESTS_DIR, "reference_flakiness.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="flaky-verify-")
HELD_OUT = os.path.join(WORK, "captures")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_flakiness  # noqa: E402


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
            report[name[: -len(".capture")]] = reference_flakiness.rank_text(handle.read())
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


def test_tool_runs_on_unseen_captures():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the three
    documented keys per entry, with each ranked test carrying its five fields."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    row_fields = ["commits", "flaky_commits", "name", "quarantine", "rate"]
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["errors", "recommend", "tests"],             "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["tests"], list), "%s: tests is not an array" % name
        assert isinstance(got["recommend"], list), "%s: recommend is not an array" % name
        assert isinstance(got["errors"], list), "%s: errors is not an array" % name
        for row in got["tests"]:
            assert isinstance(row, dict) and sorted(row) == row_fields,                 "%s: a ranked test must have exactly %s" % (name, row_fields)
            assert isinstance(row["quarantine"], bool),                 "%s/%s: quarantine is not a boolean" % (name, row["name"])
            for field in ("commits", "flaky_commits", "rate"):
                assert isinstance(row[field], int) and not isinstance(row[field], bool),                     "%s/%s/%s: not an integer" % (name, row["name"], field)
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "detail"],                 "%s: an error must have exactly code and detail" % name


def test_counts_match():
    """Criterion 3: commits counted and commits found flaky, for every test."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = {r.get("name"): (r.get("commits"), r.get("flaky_commits"))
               for r in REPORT.get(name, {}).get("tests", [])}
        expect = {r["name"]: (r["commits"], r["flaky_commits"]) for r in want["tests"]}
        if got != expect:
            wrong.append(name)
    assert not wrong, "commit counts differ in: %s" % ", ".join(sorted(wrong))


def test_ranking_order_matches():
    """Criterion 4: rate descending, then commits descending, then name."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = [r.get("name") for r in REPORT.get(name, {}).get("tests", [])]
        if got != [r["name"] for r in want["tests"]]:
            wrong.append(name)
    assert not wrong, "ranking order differs in: %s" % ", ".join(sorted(wrong))


def test_rates_and_quarantine_match():
    """Criterion 5: the floored rate and the quarantine decision, including
    tests already quarantined."""
    _compare("tests", "ranked tests")


def test_recommendations_match():
    """Criterion 6: the quarantined names, in ranking order."""
    _compare("recommend", "recommendations")


def test_errors_match():
    """Criterion 7: unknown statuses, in the order they were read."""
    _compare("errors", "errors")


def _subset(names, label):
    """Compare the whole report entry for a named set of captures."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in names:
        assert name in EXPECTED, "missing held-out capture %s" % name
        if REPORT.get(name) != EXPECTED[name]:
            wrong.append(name)
    assert not wrong, "%s differs from the specification in: %s" % (
        label, ", ".join(sorted(wrong)))


def _subset_field(names, field, label):
    """Compare one report field for a named set of captures."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in names:
        assert name in EXPECTED, "missing held-out capture %s" % name
        if REPORT.get(name, {}).get(field) != EXPECTED[name][field]:
            wrong.append(name)
    assert not wrong, "%s differs from the specification in: %s" % (
        label, ", ".join(sorted(wrong)))


def test_commit_identity_spans_runner_spellings():
    """Criterion 3: runs of one commit are one commit even when the runner
    pools spelled the SHA at different widths."""
    _subset_field(["h33", "h35"], "tests", "commit identity across SHA widths")


def test_commit_identity_is_case_insensitive():
    """Criterion 3: hex is case-insensitive, so an upper-cased abbreviation is
    the same commit as its lower-cased form."""
    _subset_field(["h33", "h34"], "tests", "commit identity across letter case")


def test_commit_identity_changes_the_ranking():
    """Criterion 4: getting commit identity right changes which test ranks
    first, not only the counts."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in ["h36"]:
        got = [r.get("name") for r in REPORT.get(name, {}).get("tests", [])]
        if got != [r["name"] for r in EXPECTED[name]["tests"]]:
            wrong.append(name)
    assert not wrong, "ranking under mixed SHA spellings differs in: %s" % (
        ", ".join(wrong))


def test_commit_identity_changes_quarantine():
    """Criteria 5 and 6: the rate, the quarantine decision and the
    recommendation all follow from commit identity."""
    _subset(["h33", "h34", "h35", "h36"], "commit-identity captures")


def test_runs_without_evidence_are_not_counted():
    """Criterion 3: a run whose outcome publishes no real results contributes
    no history, so its placeholder rows do not make a commit flaky."""
    _subset_field(["h37", "h38"], "tests", "counts under non-evidential runs")


def test_placeholder_statuses_raise_no_error():
    """Criterion 7: an unrecognised status inside a run that published no
    evidence is not an UNKNOWN_STATUS error, because the run was never read."""
    _subset_field(["h38", "h48"], "errors", "errors from non-evidential runs")


def test_test_seen_only_without_evidence_is_absent():
    """Criterion 4: a test that appears only inside runs publishing no evidence
    does not appear in the ranking at all."""
    _subset(["h39", "h40"], "captures with discarded-only history")


def test_real_builds_remain_evidence():
    """Criterion 3: builds that ran and then failed or timed out are evidence
    and must not be discarded along with the infrastructure aborts."""
    _subset(["h41"], "timed-out and failed builds")


def test_policy_in_force_beats_the_stamp():
    """Criterion 5: the bounds come from the policy revision in force when the
    capture was taken, not from the numbers stamped on the file."""
    _subset(["h42"], "a capture whose stamp lags the ledger")


def test_future_policy_revisions_are_ignored():
    """Criterion 5: a back-filled revision that had not taken effect by
    captured_at does not apply, and the ledger is not sorted."""
    _subset(["h43", "h44"], "back-filled and unsorted policy ledgers")


def test_quarantine_roster_is_resolved_by_date():
    """Criteria 5 and 6: a roster entry counts only while it is in force -
    added at or before the capture and not lifted by then."""
    _subset(["h45", "h46", "h47"], "dated quarantine rosters")


def test_all_mechanisms_together():
    """Criteria 3-7 on one capture that exercises commit spellings, run
    outcomes and as-of policy at the same time."""
    _subset(["h48"], "the combined capture")

def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
