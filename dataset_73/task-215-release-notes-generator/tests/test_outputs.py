"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_notes.py over the held-out histories in /tests/histories, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
histories, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "histories")
REFERENCE = os.path.join(TESTS_DIR, "reference_notes.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="notes-verify-")
HELD_OUT = os.path.join(WORK, "histories")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_notes  # noqa: E402

BUMPS = {"major", "minor", "patch", "none"}


def _shas(session_dir):
    """Every sha a capture mentions, so the report can be checked against it."""
    shas = {}
    for name in sorted(os.listdir(session_dir)):
        if not name.endswith(".history"):
            continue
        with open(os.path.join(os.path.realpath(session_dir), name),
                  encoding="utf-8") as handle:
            found = set()
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("op") == "commit":
                    found.add(record["sha"])
        shas[name[: -len(".history")]] = found
    return shas


def _expected(history_dir):
    if os.path.islink(history_dir):
        raise ValueError("history_dir cannot be a symlink")
    real_dir = os.path.realpath(history_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".history"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("history %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".history")]] = reference_notes.replay_text(
                handle.read())
    return report


EXPECTED = _expected(HELD_OUT)
SHAS = _shas(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(history_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(history_dir),
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


def test_tool_runs_on_unseen_histories():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the seven
    documented keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["breaking", "bump", "contributors", "errors",
                               "sections", "skipped", "version"], \
            "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["version"], str), "%s: version is not a string" % name
        assert got["bump"] in BUMPS, "%s: undocumented bump %r" % (name, got["bump"])
        for key in ("sections", "breaking", "contributors", "skipped", "errors"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for section in got["sections"]:
            assert isinstance(section, dict) and sorted(section) == ["entries", "title"], \
                "%s: a section must have exactly title and entries" % name
            for entry in section["entries"]:
                assert isinstance(entry, dict) and sorted(entry) == [
                    "breaking", "description", "pr", "scope", "sha", "type"], \
                    "%s: wrong entry keys %s" % (name, sorted(entry))
                assert entry["scope"] is None or isinstance(entry["scope"], str), \
                    "%s: scope must be a string or null" % name
                assert entry["pr"] is None or (isinstance(entry["pr"], int)
                                               and not isinstance(entry["pr"], bool)), \
                    "%s: pr must be an integer or null" % name
                assert isinstance(entry["breaking"], bool), \
                    "%s: breaking is not a boolean" % name
        for note in got["breaking"]:
            assert isinstance(note, dict) and sorted(note) == ["note", "sha"], \
                "%s: a breaking note must have exactly sha and note" % name
        for skip in got["skipped"]:
            assert isinstance(skip, dict) and sorted(skip) == ["reason", "sha"], \
                "%s: a skip must have exactly sha and reason" % name
        for error in got["errors"]:
            assert isinstance(error, dict) and sorted(error) == ["code", "detail"], \
                "%s: an error must have exactly code and detail" % name


def test_version_and_bump_match():
    """Criterion 3: the next version and the bump that produced it."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if (REPORT.get(name, {}).get("version"),
                 REPORT.get(name, {}).get("bump"))
             != (want["version"], want["bump"])]
    assert not wrong, "version or bump differs in: %s" % ", ".join(sorted(wrong))


def test_sections_match():
    """Criterion 4: the sections, in order, with their entries in order."""
    _compare("sections", "the sections")


def test_breaking_notes_match():
    """Criterion 5: the breaking changes that survived, with their notes."""
    _compare("breaking", "breaking notes")


def test_contributors_match():
    """Criterion 6: the authors credited, deduplicated and in order."""
    _compare("contributors", "contributors")


def test_skipped_commits_match():
    """Criterion 7: every commit left out, with its reason, in history order."""
    _compare("skipped", "skipped commits")


def test_errors_match():
    """Criterion 8: reverts that named nothing usable, in the order found."""
    _compare("errors", "errors")


def test_report_is_self_consistent():
    """Criterion 9: every sha mentioned comes from the capture, no sha is both
    an entry and a skip, and the bump agrees with the surviving entries."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        entries = [e for s in got.get("sections", []) for e in s.get("entries", [])]
        entry_shas = [e.get("sha") for e in entries]
        skipped_shas = [s.get("sha") for s in got.get("skipped", [])]
        known = SHAS[name]
        if any(sha not in known for sha in entry_shas + skipped_shas):
            wrong.append("%s: a sha that is not in the capture" % name)
        if set(entry_shas) & set(skipped_shas):
            wrong.append("%s: a sha is both an entry and a skip" % name)
        if len(entry_shas) != len(set(entry_shas)):
            wrong.append("%s: an entry appears twice" % name)
        expected_bump = ("major" if any(e.get("breaking") for e in entries)
                         else "minor" if any(e.get("type") == "feat" for e in entries)
                         else "patch" if entries else "none")
        if got.get("bump") != expected_bump:
            wrong.append("%s: bump %r does not follow from the entries"
                         % (name, got.get("bump")))
    assert not wrong, "; ".join(sorted(set(wrong)))


def test_sample_report_is_reproduced():
    """Criterion 10: running the tool on /app/samples reproduces
    expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
