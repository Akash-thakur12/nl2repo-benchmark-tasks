"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_rollup.py over the held-out captures in /tests/captures, so no
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
REFERENCE = os.path.join(TESTS_DIR, "reference_rollup.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="rollup-verify-")
HELD_OUT = os.path.join(WORK, "captures")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_rollup  # noqa: E402


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
            report[name[: -len(".capture")]] = reference_rollup.rollup_text(handle.read())
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



def _rows_of_type(report, name, kind):
    return [r for r in report.get(name, {}).get("rows", []) if r.get("type") == kind]


def _compare_type(kind, label):
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        expected_rows = [r for r in want["rows"] if r["type"] == kind]
        if _rows_of_type(REPORT, name, kind) != expected_rows:
            wrong.append(name)
    assert not wrong, "%s rows differ from the specification in: %s" % (
        label, ", ".join(sorted(wrong)))


def test_tool_runs_on_unseen_captures():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the two documented
    keys per entry, with rows carrying the fields their type defines."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    common = ["series", "tier", "type", "window"]
    fields = {
        "counter": sorted(common + ["delta"]),
        "gauge": sorted(common + ["min", "max", "last", "count", "sum", "avg"]),
        "histogram": sorted(common + ["boundaries", "counts"]),
    }
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["errors", "rows"], "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["rows"], list), "%s: rows is not an array" % name
        assert isinstance(got["errors"], list), "%s: errors is not an array" % name
        for row in got["rows"]:
            assert isinstance(row, dict), "%s: a row is not an object" % name
            kind = row.get("type")
            assert kind in fields, "%s: unknown row type %r" % (name, kind)
            assert sorted(row) == fields[kind],                 "%s: a %s row must have exactly %s" % (name, kind, fields[kind])
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "series"],                 "%s: an error must have exactly code and series" % name


def test_row_ordering_matches():
    """Criterion 3: rows ordered by tier as configured, then by series key, then
    by window start."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = [(r.get("tier"), r.get("series"), r.get("window"))
               for r in REPORT.get(name, {}).get("rows", [])]
        if got != [(r["tier"], r["series"], r["window"]) for r in want["rows"]]:
            wrong.append(name)
    assert not wrong, "row ordering differs in: %s" % ", ".join(sorted(wrong))


def test_counter_rows_match():
    """Criterion 4: counter deltas, with baselines carried across windows and
    resets accounted for."""
    _compare_type("counter", "counter")


def test_gauge_rows_match():
    """Criterion 5: gauge min, max, last, count, sum and the half-to-even
    average."""
    _compare_type("gauge", "gauge")


def test_histogram_rows_match():
    """Criterion 6: histogram boundaries and element-wise counts."""
    _compare_type("histogram", "histogram")


def test_errors_match():
    """Criterion 7: series that dropped out, ordered by series key."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if REPORT.get(name, {}).get("errors") != want["errors"]]
    assert not wrong, "errors differ in: %s" % ", ".join(sorted(wrong))


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
