"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_validator.py over the held-out drops in /tests/drops, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
drops, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "drops")
REFERENCE = os.path.join(TESTS_DIR, "reference_validator.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="drops-verify-")
HELD_OUT = os.path.join(WORK, "drops")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_validator  # noqa: E402


def _expected(drop_dir):
    if os.path.islink(drop_dir):
        raise ValueError("drop_dir cannot be a symlink")
    real_dir = os.path.realpath(drop_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".drop"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("scenario %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".drop")]] = reference_validator.validate_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(drop_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(drop_dir), out_path],
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



def test_tool_runs_on_unseen_drops():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of drops it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per drop, exactly the five documented
    keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "drop keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["accepted", "extra_columns", "quarantined",
                              "reject_reason", "status", "totals"][:6],             "%s: wrong keys %s" % (name, sorted(got))
        assert got["status"] in ("ok", "rejected"), "%s: bad status" % name
        assert isinstance(got["accepted"], list), "%s: accepted is not an array" % name
        assert isinstance(got["quarantined"], list), "%s: quarantined is not an array" % name
        assert isinstance(got["extra_columns"], list), "%s: extra_columns is not an array" % name
        assert isinstance(got["totals"], dict), "%s: totals is not an object" % name
        assert sorted(got["totals"]) == ["accepted", "data_rows", "quarantined"],             "%s: totals must have exactly data_rows, accepted and quarantined" % name
        for entry in got["quarantined"]:
            assert isinstance(entry, dict) and sorted(entry) == ["column", "line", "reason"],                 "%s: a quarantine entry must have exactly line, reason and column" % name


def _compare(field, label):
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if REPORT.get(name, {}).get(field) != want[field]]
    assert not wrong, "%s differs from the specification in: %s" % (label, ", ".join(sorted(wrong)))


def test_status_and_reject_reason_match():
    """Criterion 3: a drop is rejected exactly when the header demands it, with
    the documented reason."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if (REPORT.get(name, {}).get("status"), REPORT.get(name, {}).get("reject_reason"))
             != (want["status"], want["reject_reason"])]
    assert not wrong, "status or reject_reason differs in: %s" % ", ".join(sorted(wrong))


def test_accepted_rows_match():
    """Criterion 4: accepted rows, in file order, with one member per schema
    column carrying the parsed value."""
    _compare("accepted", "accepted rows")


def test_quarantined_rows_match():
    """Criterion 5: quarantined rows, in file order, with the right line, reason
    and column."""
    _compare("quarantined", "quarantined rows")


def test_extra_columns_match():
    """Criterion 6: header columns not named in the schema, in header order."""
    _compare("extra_columns", "extra_columns")


def test_totals_match_and_reconcile():
    """Criterion 7: data_rows, accepted and quarantined, with the last two
    summing to the first."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        totals = REPORT.get(name, {}).get("totals")
        if totals != want["totals"]:
            wrong.append(name)
        elif totals["accepted"] + totals["quarantined"] != totals["data_rows"]:
            wrong.append(name + " (does not reconcile)")
    assert not wrong, "totals differ in: %s" % ", ".join(sorted(wrong))


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"


def _subset(names, fields, label):
    """Compare only `fields` for only the named drops, so a partly correct
    implementation still scores the tests it does satisfy."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in names:
        want = EXPECTED[name]
        got = REPORT.get(name, {})
        for field in fields:
            if got.get(field) != want[field]:
                wrong.append("%s.%s: expected %r, got %r"
                             % (name, field, want[field], got.get(field)))
    assert not wrong, "%s\n  %s" % (label, "\n  ".join(wrong))


def test_quarantine_line_is_where_the_record_starts():
    """Criterion 5: a record whose quoted field contains a line break still
    reports the line of the drop body the record begins on."""
    _subset(["h03", "h09"], ["quarantined"],
            "quarantine lines are wrong on drops with quoted line breaks")


def test_line_numbers_survive_blank_lines_and_multiline_records():
    """Criterion 5: blank lines and multiline records shift every later
    quarantine line together, and the totals still reconcile."""
    _subset(["h10", "h31"], ["quarantined", "totals"],
            "quarantine lines or totals are wrong once blank lines and "
            "multiline records are mixed")


def test_range_limits_use_the_revision_in_force_at_capture():
    """Criterion 5: range limits come from the revision in force when the drop
    was captured, not from the newest revision and not from the drop's cache."""
    _subset(["h19"], ["accepted", "quarantined", "totals"],
            "range limits are not resolved as of the capture instant")


def test_range_limits_are_resolved_per_partner():
    """Criterion 4: limits are agreed per partner, so the same value can be in
    range for one partner and out of range for another."""
    _subset(["h29"], ["accepted", "quarantined", "extra_columns"],
            "range limits are not resolved per partner")


def test_range_bounds_are_inclusive():
    """Criterion 5: both bounds of the limits in force are inclusive."""
    _subset(["h20"], ["accepted", "quarantined"],
            "the bounds in force are not treated as inclusive")


def test_failing_column_is_the_first_in_schema_order():
    """Criterion 5: when a row has several invalid columns the quarantine entry
    names the first one in schema order, whatever the header order is."""
    _subset(["h27", "h28", "h32"], ["quarantined"],
            "the wrong column is named when a row has several failures")


def test_rfc4180_quoting_is_honoured():
    """Criterion 4: quoted commas, doubled quotes, a quote that is not at the
    start of a field, an empty quoted field and embedded line breaks."""
    _subset(["h01", "h02", "h04", "h05", "h09"], ["accepted", "totals"],
            "RFC 4180 quoting is not read correctly")


def test_header_reconciliation():
    """Criterion 6: reordered, extra, missing and duplicated header names."""
    _subset(["h11", "h12", "h13", "h14", "h15", "h30"],
            ["status", "reject_reason", "extra_columns", "accepted"],
            "header reconciliation differs from the specification")


def test_type_parsers_are_strict():
    """Criterion 4: decimals keep their original text, dates are checked
    against the calendar, and booleans are lower case only."""
    _subset(["h21", "h22", "h23"], ["accepted", "quarantined"],
            "the type parsers are not strict enough")
