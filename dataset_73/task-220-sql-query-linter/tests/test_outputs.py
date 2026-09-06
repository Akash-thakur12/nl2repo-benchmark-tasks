"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_lint.py over the held-out captures in /tests/lints, so no
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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "lints")
REFERENCE = os.path.join(TESTS_DIR, "reference_lint.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="lint-verify-")
HELD_OUT = os.path.join(WORK, "lints")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_lint  # noqa: E402

SEVERITIES = {"error", "warning", "style"}
CODES = {"UNKNOWN_RULE", "UNKNOWN_SEVERITY"}


def _queries(capture_dir):
    """The query names and their text, in capture order."""
    found = {}
    for name in sorted(os.listdir(capture_dir)):
        if not name.endswith(".lint"):
            continue
        with open(os.path.join(os.path.realpath(capture_dir), name),
                  encoding="utf-8") as handle:
            listed = []
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("op") == "query":
                    listed.append((record["name"], record["sql"]))
        found[name[: -len(".lint")]] = listed
    return found


def _expected(capture_dir):
    if os.path.islink(capture_dir):
        raise ValueError("capture_dir cannot be a symlink")
    real_dir = os.path.realpath(capture_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".lint"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("capture %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".lint")]] = reference_lint.replay_text(
                handle.read())
    return report


EXPECTED = _expected(HELD_OUT)
QUERIES = _queries(HELD_OUT)

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
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(capture_dir),
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


def test_tool_runs_on_unseen_captures():
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
        assert sorted(got) == ["errors", "queries", "totals"], \
            "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["queries"], list), "%s: queries is not an array" % name
        assert isinstance(got["errors"], list), "%s: errors is not an array" % name
        assert isinstance(got["totals"], dict) and sorted(got["totals"]) == [
            "error", "style", "warning"], "%s: totals has the wrong keys" % name
        for entry in got["queries"]:
            assert isinstance(entry, dict) and sorted(entry) == ["counts", "name",
                                                                 "violations"], \
                "%s: a query must have exactly name, violations and counts" % name
            assert sorted(entry["counts"]) == ["error", "style", "warning"], \
                "%s: counts has the wrong keys" % name
            for violation in entry["violations"]:
                assert isinstance(violation, dict) and sorted(violation) == [
                    "column", "line", "rule", "severity"], \
                    "%s: wrong violation keys %s" % (name, sorted(violation))
                assert violation["severity"] in SEVERITIES, \
                    "%s: undocumented severity %r" % (name, violation["severity"])
        for error in got["errors"]:
            assert isinstance(error, dict) and sorted(error) == ["code", "detail"], \
                "%s: an error must have exactly code and detail" % name
            assert error["code"] in CODES, \
                "%s: undocumented error code %r" % (name, error["code"])


def test_violations_match():
    """Criterion 3: the same rules at the same places, in the documented
    order."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if [[(v.get("line"), v.get("column"), v.get("rule"))
                  for v in q.get("violations", [])]
                 for q in REPORT.get(name, {}).get("queries", [])]
             != [[(v["line"], v["column"], v["rule"]) for v in q["violations"]]
                 for q in want["queries"]]]
    assert not wrong, "the violations differ in: %s" % ", ".join(sorted(wrong))


def test_severities_match():
    """Criterion 4: every violation's severity, default or configured."""
    _compare("queries", "the violation severities")


def test_counts_match():
    """Criterion 5: each query's counts."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if [q.get("counts") for q in REPORT.get(name, {}).get("queries", [])]
             != [q["counts"] for q in want["queries"]]]
    assert not wrong, "the counts differ in: %s" % ", ".join(sorted(wrong))


def test_totals_match():
    """Criterion 6: the totals over every query."""
    _compare("totals", "the totals")


def test_errors_match():
    """Criterion 7: configuration errors, in the order the configuration lists
    them."""
    _compare("errors", "errors")


def test_report_is_self_consistent():
    """Criterion 8: the queries the capture names, positions inside the text,
    counts that agree with the violations, and totals that add up."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        listed = QUERIES[name]
        entries = got.get("queries", [])
        if [q.get("name") for q in entries] != [n for n, _ in listed]:
            wrong.append("%s: the queries are not the ones the capture names" % name)
            continue
        running = {"error": 0, "warning": 0, "style": 0}
        for entry, (_, sql) in zip(entries, listed):
            lines = sql.split("\n")
            counted = {"error": 0, "warning": 0, "style": 0}
            for violation in entry.get("violations", []):
                line = violation.get("line")
                column = violation.get("column")
                if not isinstance(line, int) or isinstance(line, bool) \
                        or not 1 <= line <= len(lines):
                    wrong.append("%s: a violation is not on a line of the query"
                                 % name)
                    continue
                if not isinstance(column, int) or isinstance(column, bool) \
                        or not 1 <= column <= max(1, len(lines[line - 1])):
                    wrong.append("%s: a violation is not at a column of the line"
                                 % name)
                    continue
                counted[violation["severity"]] += 1
            if entry.get("counts") != counted:
                wrong.append("%s: the counts do not match the violations" % name)
            for key in running:
                running[key] += counted[key]
        if got.get("totals") != running:
            wrong.append("%s: the totals do not add up" % name)
    assert not wrong, "; ".join(sorted(set(wrong)))


def test_sample_report_is_reproduced():
    """Criterion 9: running the tool on /app/samples reproduces
    expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
