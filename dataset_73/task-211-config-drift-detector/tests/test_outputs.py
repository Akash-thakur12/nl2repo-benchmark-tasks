"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_drift.py over the held-out states in /tests/states, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
states, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "states")
REFERENCE = os.path.join(TESTS_DIR, "reference_drift.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="drift-verify-")
HELD_OUT = os.path.join(WORK, "states")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_drift  # noqa: E402


def _expected(state_dir):
    if os.path.islink(state_dir):
        raise ValueError("state_dir cannot be a symlink")
    real_dir = os.path.realpath(state_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".state"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("scenario %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".state")]] = reference_drift.detect_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(state_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(state_dir), out_path],
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


def test_tool_runs_on_unseen_states():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the three
    documented keys per entry, with the two values present only on CHANGED."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["counts", "drift", "errors"],             "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["drift"], list), "%s: drift is not an array" % name
        assert isinstance(got["counts"], dict), "%s: counts is not an object" % name
        assert isinstance(got["errors"], list), "%s: errors is not an array" % name
        for finding in got["drift"]:
            assert isinstance(finding, dict), "%s: a finding is not an object" % name
            kind = finding.get("kind")
            assert kind in ("MISSING", "UNMANAGED", "CHANGED", "ADDED", "REMOVED"),                 "%s: unknown kind %r" % (name, kind)
            wanted = ["kind", "path", "resource"]
            if kind == "CHANGED":
                wanted = sorted(wanted + ["declared", "live"])
            assert sorted(finding) == wanted,                 "%s: a %s finding must have exactly %s" % (name, kind, wanted)
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "detail"],                 "%s: an error must have exactly code and detail" % name


def test_findings_match():
    """Criterion 3: every finding, with its resource, path, kind and, where the
    kind calls for them, the two values."""
    _compare("drift", "findings")


def test_finding_order_matches():
    """Criterion 4: ordered by resource id, then by path, the empty path first."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = [(f.get("resource"), f.get("path"))
               for f in REPORT.get(name, {}).get("drift", [])]
        if got != [(f["resource"], f["path"]) for f in want["drift"]]:
            wrong.append(name)
    assert not wrong, "finding order differs in: %s" % ", ".join(sorted(wrong))


def test_counts_match():
    """Criterion 5: one entry per kind that occurred, and none for kinds that
    did not."""
    _compare("counts", "counts")


def test_counts_reconcile():
    """Criterion 6: the counts add up to the findings they describe."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        tally = {}
        for finding in got.get("drift", []):
            tally[finding.get("kind")] = tally.get(finding.get("kind"), 0) + 1
        if tally != got.get("counts"):
            wrong.append(name)
    assert not wrong, "counts do not reconcile in: %s" % ", ".join(sorted(wrong))


def test_errors_match():
    """Criterion 7: duplicate ids on either side, in the order they were read."""
    _compare("errors", "errors")


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
