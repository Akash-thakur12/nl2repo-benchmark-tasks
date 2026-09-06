"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_registry.py over the held-out sessions in /tests/registries, so
no expected value is hardcoded. Both are removed from disk before the candidate
is invoked, and the candidate runs from a scratch directory over a copy of the
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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "registries")
REFERENCE = os.path.join(TESTS_DIR, "reference_registry.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="registry-verify-")
HELD_OUT = os.path.join(WORK, "registries")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_registry  # noqa: E402

CODES = {"UNKNOWN_SUBJECT", "UNKNOWN_VERSION", "INCOMPATIBLE", "INVALID_LEVEL"}
FIELDS = {
    "register": ["created", "id", "op", "subject", "version"],
    "check": ["compatible", "op", "subject"],
    "lookup": ["id", "op", "subject", "version"],
    "delete_version": ["op", "subject", "version"],
    "set_compatibility": ["level", "op", "subject"],
}


def _schemas(registry_dir):
    """Every schema a capture registers, so ids can be checked for collisions."""
    seen = {}
    for name in sorted(os.listdir(registry_dir)):
        if not name.endswith(".registry"):
            continue
        with open(os.path.join(os.path.realpath(registry_dir), name),
                  encoding="utf-8") as handle:
            marks = []
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("op") == "register":
                    marks.append(json.dumps(record["schema"], sort_keys=True))
        seen[name[: -len(".registry")]] = marks
    return seen


def _expected(registry_dir):
    if os.path.islink(registry_dir):
        raise ValueError("registry_dir cannot be a symlink")
    real_dir = os.path.realpath(registry_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".registry"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("session %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".registry")]] = reference_registry.replay_text(
                handle.read())
    return report


EXPECTED = _expected(HELD_OUT)
REGISTERED = _schemas(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(registry_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(registry_dir),
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


def test_tool_runs_on_unseen_sessions():
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
        assert sorted(got) == ["errors", "results", "subjects"], \
            "%s: wrong keys %s" % (name, sorted(got))
        for key in ("results", "subjects", "errors"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for result in got["results"]:
            assert isinstance(result, dict) and result.get("op") in FIELDS, \
                "%s: a result must name a documented operation" % name
            assert sorted(result) == FIELDS[result["op"]], \
                "%s: wrong fields for %s: %s" % (name, result["op"], sorted(result))
        for subject in got["subjects"]:
            assert isinstance(subject, dict) and sorted(subject) == [
                "compatibility", "name", "versions"], \
                "%s: a subject must have exactly name, compatibility and versions" % name
            for version in subject["versions"]:
                assert isinstance(version, dict) and sorted(version) == ["id",
                                                                         "version"], \
                    "%s: a version must have exactly version and id" % name
        for error in got["errors"]:
            assert isinstance(error, dict) and sorted(error) == ["code", "detail"], \
                "%s: an error must have exactly code and detail" % name
            assert error["code"] in CODES, \
                "%s: undocumented error code %r" % (name, error["code"])


def test_results_match():
    """Criterion 3: one entry per operation, in capture order, with the fields
    that operation reports."""
    _compare("results", "the operation results")


def test_registration_outcomes_match():
    """Criterion 4: which registrations created a version, and what version and
    id each returned."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = [r for r in REPORT.get(name, {}).get("results", [])
               if r.get("op") == "register"]
        expect = [r for r in want["results"] if r["op"] == "register"]
        if [(r.get("version"), r.get("id"), r.get("created")) for r in got] != \
                [(r["version"], r["id"], r["created"]) for r in expect]:
            wrong.append(name)
    assert not wrong, "registration outcomes differ in: %s" % ", ".join(sorted(wrong))


def test_subjects_match():
    """Criterion 5: the subjects in order, their levels, and what is left of
    each."""
    _compare("subjects", "the subjects")


def test_errors_match():
    """Criterion 6: every error, in the order it happened."""
    _compare("errors", "errors")


def test_report_is_self_consistent():
    """Criterion 7: version numbers that increase and never repeat, versions
    that a registration actually returned, and ids that never name two
    different schemas."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        created = {}
        for result in got.get("results", []):
            if result.get("op") == "register" and result.get("version") is not None:
                created.setdefault(result.get("subject"), set()).add(
                    (result.get("version"), result.get("id")))
        for subject in got.get("subjects", []):
            numbers = [v.get("version") for v in subject.get("versions", [])]
            if numbers != sorted(numbers) or len(numbers) != len(set(numbers)):
                wrong.append("%s: %s has repeated or unordered versions"
                             % (name, subject.get("name")))
            known = created.get(subject.get("name"), set())
            if any((v.get("version"), v.get("id")) not in known
                   for v in subject.get("versions", [])):
                wrong.append("%s: %s lists a version no registration returned"
                             % (name, subject.get("name")))

        by_id = {}
        for index, result in enumerate(got.get("results", [])):
            if result.get("op") == "register" and result.get("id") is not None \
                    and result.get("created"):
                mark = REGISTERED[name][
                    len([r for r in got["results"][:index + 1]
                         if r.get("op") == "register"]) - 1]
                if by_id.setdefault(result["id"], mark) != mark:
                    wrong.append("%s: id %s names two different schemas"
                                 % (name, result["id"]))
    assert not wrong, "; ".join(sorted(set(wrong)))


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces
    expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
