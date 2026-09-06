"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_review.py over the held-out reviews in /tests/reviews, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
reviews, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "reviews")
REFERENCE = os.path.join(TESTS_DIR, "reference_review.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="review-verify-")
HELD_OUT = os.path.join(WORK, "reviews")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_review  # noqa: E402

STATES = {"APPROVED", "REVOKED", "STILL_INHERITED", "UNREVIEWED",
          "AUTO_REVOKED", "TERMINATED"}
GONE = {"REVOKED", "AUTO_REVOKED", "TERMINATED"}
CODES = {"UNKNOWN_GROUP", "MEMBERSHIP_CYCLE", "UNKNOWN_USER", "TERMINATED_USER",
         "NO_SUCH_ACCESS", "DUPLICATE_DECISION"}


def _users(review_dir):
    """The user names each capture defines, in directory order."""
    found = {}
    for name in sorted(os.listdir(review_dir)):
        if not name.endswith(".review"):
            continue
        with open(os.path.join(os.path.realpath(review_dir), name),
                  encoding="utf-8") as handle:
            names = []
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("op") == "user":
                    names.append(record["name"])
        found[name[: -len(".review")]] = names
    return found


def _expected(review_dir):
    if os.path.islink(review_dir):
        raise ValueError("review_dir cannot be a symlink")
    real_dir = os.path.realpath(review_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".review"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("review %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".review")]] = reference_review.replay_text(
                handle.read())
    return report


EXPECTED = _expected(HELD_OUT)
USERS = _users(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(review_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(review_dir),
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


def test_tool_runs_on_unseen_reviews():
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
        assert sorted(got) == ["access", "errors", "violations"], \
            "%s: wrong keys %s" % (name, sorted(got))
        for key in ("access", "violations", "errors"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for row in got["access"]:
            assert isinstance(row, dict) and sorted(row) == [
                "effective", "entitlement", "source", "state", "user", "via"], \
                "%s: wrong access keys %s" % (name, sorted(row))
            assert row["source"] in ("DIRECT", "GROUP"), \
                "%s: undocumented source %r" % (name, row["source"])
            assert row["via"] is None or isinstance(row["via"], str), \
                "%s: via must be a group name or null" % name
            assert row["state"] in STATES, \
                "%s: undocumented state %r" % (name, row["state"])
            assert isinstance(row["effective"], bool), \
                "%s: effective is not a boolean" % name
        for violation in got["violations"]:
            assert isinstance(violation, dict) and sorted(violation) == [
                "entitlements", "user"], \
                "%s: a violation must have exactly user and entitlements" % name
            assert isinstance(violation["entitlements"], list) \
                and len(violation["entitlements"]) == 2, \
                "%s: a violation names exactly two entitlements" % name
        for error in got["errors"]:
            assert isinstance(error, dict) and sorted(error) == ["code", "detail"], \
                "%s: an error must have exactly code and detail" % name
            assert error["code"] in CODES, \
                "%s: undocumented error code %r" % (name, error["code"])


def test_access_rows_match():
    """Criterion 3: the same rows in the same order, with the same source and
    via."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if [(r.get("user"), r.get("entitlement"), r.get("source"), r.get("via"))
                 for r in REPORT.get(name, {}).get("access", [])]
             != [(r["user"], r["entitlement"], r["source"], r["via"])
                 for r in want["access"]]]
    assert not wrong, "the access rows differ in: %s" % ", ".join(sorted(wrong))


def test_states_match():
    """Criterion 4: every row's state, and whether the access survives."""
    _compare("access", "the access states")


def test_violations_match():
    """Criterion 5: who is left holding two things they should not hold
    together."""
    _compare("violations", "the violations")


def test_errors_match():
    """Criterion 6: every error, cycles first and the rest in order."""
    _compare("errors", "errors")


def test_report_is_self_consistent():
    """Criterion 7: known users, no pair twice, effective agreeing with the
    state, and violations naming access the report itself shows."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        known = USERS[name]
        rows = got.get("access", [])
        pairs = [(r.get("user"), r.get("entitlement")) for r in rows]
        if any(who not in known for who, _ in pairs):
            wrong.append("%s: a user who is not in the directory" % name)
        if len(pairs) != len(set(pairs)):
            wrong.append("%s: a user and entitlement pair appears twice" % name)
        for row in rows:
            if row.get("effective") != (row.get("state") not in GONE):
                wrong.append("%s: effective disagrees with state %r"
                             % (name, row.get("state")))
        standing = {(r.get("user"), r.get("entitlement")) for r in rows
                    if r.get("effective")}
        for violation in got.get("violations", []):
            who = violation.get("user")
            if any((who, entitlement) not in standing
                   for entitlement in violation.get("entitlements", [])):
                wrong.append("%s: a violation names access the report does not "
                             "show %s holding" % (name, who))
    assert not wrong, "; ".join(sorted(set(wrong)))


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces
    expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
