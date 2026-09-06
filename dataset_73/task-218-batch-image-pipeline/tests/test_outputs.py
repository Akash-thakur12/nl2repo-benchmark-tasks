"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_pipeline.py over the held-out manifests in /tests/manifests, so
no expected value is hardcoded. Both are removed from disk before the candidate
is invoked, and the candidate runs from a scratch directory over a copy of the
manifests, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "manifests")
REFERENCE = os.path.join(TESTS_DIR, "reference_pipeline.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="pipeline-verify-")
HELD_OUT = os.path.join(WORK, "manifests")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_pipeline  # noqa: E402

REASONS = {"TOO_SMALL", "CROP_OUT_OF_BOUNDS", "NAME_COLLISION"}
WARNINGS = {"ALPHA_FLATTENED", "FRAMES_DROPPED", "QUALITY_IGNORED"}
FORMATS = {"jpeg", "png", "webp", "gif"}


def _sources(manifest_dir):
    """The source names each capture declares, in order."""
    found = {}
    for name in sorted(os.listdir(manifest_dir)):
        if not name.endswith(".manifest"):
            continue
        with open(os.path.join(os.path.realpath(manifest_dir), name),
                  encoding="utf-8") as handle:
            names = [json.loads(line)["name"] for line in handle
                     if line.strip() and json.loads(line).get("op") == "source"]
        found[name[: -len(".manifest")]] = names
    return found


def _expected(manifest_dir):
    if os.path.islink(manifest_dir):
        raise ValueError("manifest_dir cannot be a symlink")
    real_dir = os.path.realpath(manifest_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".manifest"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("manifest %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".manifest")]] = reference_pipeline.replay_text(
                handle.read())
    return report


EXPECTED = _expected(HELD_OUT)
SOURCES = _sources(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(manifest_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(manifest_dir),
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


def test_tool_runs_on_unseen_manifests():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the four
    documented keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    for name in EXPECTED:
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["errors", "outputs", "skipped", "warnings"], \
            "%s: wrong keys %s" % (name, sorted(got))
        for key in ("outputs", "skipped", "warnings", "errors"):
            assert isinstance(got[key], list), "%s: %s is not an array" % (name, key)
        for output in got["outputs"]:
            assert isinstance(output, dict) and sorted(output) == [
                "format", "height", "name", "source", "width"], \
                "%s: wrong output keys %s" % (name, sorted(output))
            assert output["format"] in FORMATS, \
                "%s: undocumented format %r" % (name, output["format"])
        for skip in got["skipped"]:
            assert isinstance(skip, dict) and sorted(skip) == ["reason", "source"], \
                "%s: a skip must have exactly source and reason" % name
            assert skip["reason"] in REASONS, \
                "%s: undocumented reason %r" % (name, skip["reason"])
        for warning in got["warnings"]:
            assert isinstance(warning, dict) and sorted(warning) == ["code",
                                                                     "source"], \
                "%s: a warning must have exactly source and code" % name
            assert warning["code"] in WARNINGS, \
                "%s: undocumented warning %r" % (name, warning["code"])
        for error in got["errors"]:
            assert isinstance(error, dict) and sorted(error) == ["code", "detail"], \
                "%s: an error must have exactly code and detail" % name


def test_outputs_match():
    """Criterion 3: the outputs, in manifest order, with their names and
    formats."""
    _compare("outputs", "the outputs")


def test_output_sizes_match():
    """Criterion 4: the final width and height of every output."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if [(o.get("source"), o.get("width"), o.get("height"))
                 for o in REPORT.get(name, {}).get("outputs", [])]
             != [(o["source"], o["width"], o["height"]) for o in want["outputs"]]]
    assert not wrong, "output sizes differ in: %s" % ", ".join(sorted(wrong))


def test_skipped_sources_match():
    """Criterion 5: every source left out, with its reason, in manifest
    order."""
    _compare("skipped", "the skipped sources")


def test_warnings_match():
    """Criterion 6: every warning, in the order it was recorded."""
    _compare("warnings", "the warnings")


def test_errors_match():
    """Criterion 7: every error."""
    _compare("errors", "errors")


def test_report_is_self_consistent():
    """Criterion 8: each source used once, only sources from the manifest, no
    two outputs sharing a name, and every length a positive integer."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in EXPECTED:
        got = REPORT.get(name, {})
        known = SOURCES[name]
        used = [o.get("source") for o in got.get("outputs", [])] + \
               [s.get("source") for s in got.get("skipped", [])]
        if any(source not in known for source in used):
            wrong.append("%s: a source that is not in the manifest" % name)
        for source in set(used):
            if used.count(source) > known.count(source):
                wrong.append("%s: %s is accounted for more than once"
                             % (name, source))
        names = [o.get("name") for o in got.get("outputs", [])]
        if len(names) != len(set(names)):
            wrong.append("%s: two outputs share a name" % name)
        for output in got.get("outputs", []):
            for key in ("width", "height"):
                value = output.get(key)
                if not isinstance(value, int) or isinstance(value, bool) \
                        or value < 1:
                    wrong.append("%s: %s is not a positive integer" % (name, key))
    assert not wrong, "; ".join(sorted(set(wrong)))


def test_sample_report_is_reproduced():
    """Criterion 9: running the tool on /app/samples reproduces
    expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
