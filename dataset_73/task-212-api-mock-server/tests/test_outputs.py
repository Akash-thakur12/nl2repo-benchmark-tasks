"""Behaviour tests for /app/run.sh, one test per specification criterion.

Ground truth is derived here by running the reference model in
/tests/reference_mock.py over the held-out captures in /tests/captures, so no
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
REFERENCE = os.path.join(TESTS_DIR, "reference_mock.py")

# The paths the task image uses. The overrides exist so tools/check_crux.py can
# drive this same suite against a deliberately wrong engine; nothing sets them
# in the image.
TOOL = os.environ.get("MOCK_TOOL", "/app/run.sh")
SAMPLES = os.environ.get("MOCK_SAMPLES", "/app/samples")
RECORDINGS = os.environ.get("MOCK_REFERENCE", "/app/reference")

WORK = tempfile.mkdtemp(prefix="mock-verify-")
HELD_OUT = os.path.join(WORK, "captures")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_mock  # noqa: E402


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
            report[name[: -len(".capture")]] = reference_mock.serve_text(handle.read())
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


def _check(names, what):
    """Compare the whole entry - responses and matched - for named captures."""
    assert REPORT is not None, ERROR
    wrong = []
    for name in names:
        if REPORT.get(name) != EXPECTED[name]:
            wrong.append(name)
    assert not wrong, "%s: wrong in %s" % (what, ", ".join(sorted(wrong)))


# --------------------------------------------------------------- the tool runs
def test_tool_runs_on_unseen_captures():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of captures it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per capture, exactly the two documented
    keys per entry, with one response and one match per request."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "capture keys differ"
    for name, want in EXPECTED.items():
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["matched", "responses"], \
            "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["responses"], list), "%s: responses is not an array" % name
        assert isinstance(got["matched"], list), "%s: matched is not an array" % name
        assert len(got["responses"]) == len(want["responses"]), \
            "%s: wrong number of responses" % name
        assert len(got["matched"]) == len(got["responses"]), \
            "%s: matched and responses are different lengths" % name
        for entry in got["responses"]:
            assert isinstance(entry, dict) and sorted(entry) == ["body", "headers", "status"], \
                "%s: a response must have exactly status, body and headers" % name
            assert isinstance(entry["status"], int) and not isinstance(entry["status"], bool), \
                "%s: status is not an integer" % name
            assert isinstance(entry["headers"], dict), \
                "%s: headers is not an object" % name
        for entry in got["matched"]:
            assert entry is None or (isinstance(entry, int) and not isinstance(entry, bool)), \
                "%s: a match must be an integer or null" % name


def test_report_is_deterministic():
    """Criterion 1: replaying the same directory twice gives the same report."""
    assert REPORT is not None, ERROR
    again, error = _run(HELD_OUT, "held-out-again.json")
    assert again is not None, error
    assert again == REPORT, "two runs over the same captures disagree"


# ----------------------------------------------------------- global comparisons
def test_statuses_match():
    """Criterion 3: the status of every response, in request order."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = [r.get("status") for r in REPORT.get(name, {}).get("responses", [])]
        if got != [r["status"] for r in want["responses"]]:
            wrong.append(name)
    assert not wrong, "statuses differ in: %s" % ", ".join(sorted(wrong))


def test_bodies_and_headers_match():
    """Criterion 4: the body and headers of every response, including the allow
    header on a refused method."""
    _compare("responses", "responses")


def test_matched_routes_match():
    """Criterion 5: which route answered each request, or null when none did."""
    _compare("matched", "matched routes")


def test_sample_report_is_reproduced():
    """Criterion 6: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"


def test_recorded_report_is_reproduced():
    """Criterion 7: running the tool on /app/reference reproduces
    recorded.json, the report the live mock produced for those captures."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(RECORDINGS, "recorded.json")
    assert report is not None, error
    with open(os.path.join(RECORDINGS, "recorded.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "recorded report does not match"


# ------------------------------------------------------------ matching a route
def test_path_matching_family():
    """Criteria 3-5, spec 1.2, 1.3 and 2.2: segment counts, a trailing slash as
    a segment, case-sensitive literals, and a 404 when nothing matches."""
    _check(["h01", "h02", "h03", "h10", "h11", "h12", "h13"], "path matching")


def test_validation_and_fixture_family():
    """Criteria 3-5, spec 3, 4 and 5: query and body schemas in declared order,
    strict types, unknown fields, fixture conditions and fixture limits."""
    _check(["h14", "h15", "h16", "h17", "h18", "h19", "h20",
            "h21", "h22", "h23", "h24", "h25", "h26", "h27",
            "h28", "h29", "h30", "h31", "h32", "h33", "h34",
            "h35", "h36", "h37", "h39"], "validation and fixtures")


# ---------------------------------------------------------- route precedence
def test_precedence_identical_shapes_use_declaration_order():
    """Spec 2.4 and gateway-routing.md row 4: two templates of identical shape
    are separated by declaration order, earliest first."""
    _check(["h09", "h43"], "identical-shape tie-break")


def test_precedence_is_not_a_count_of_literal_segments():
    """Spec 2.4 and gateway-routing.md row 1: a template with three literal
    segments loses to one with a single literal in the leftmost segment."""
    _check(["h07", "h08", "h40"], "leftmost-literal precedence")


def test_precedence_when_literal_counts_and_prefixes_tie():
    """Spec 2.4 and gateway-routing.md rows 2 and 3: two templates with the same
    number of literals, and the same run of leading literals, are still
    separated by the leftmost segment where they differ."""
    _check(["h41", "h42"], "precedence with equal counts")


def test_precedence_among_more_than_two_candidates():
    """Spec 2.4 and gateway-routing.md note 2: with three overlapping templates
    the winner is the one that beats every other, and it is chosen from the
    candidates left after the method filter of 2.3, not before it."""
    _check(["h44", "h45", "h46"], "three-way precedence")


# ------------------------------------------------------------- the counter
def test_handling_order_follows_the_counter():
    """Spec 7.1 and capture-format.md: the mock handled the requests in counter
    order, so a fixture limit is spent on the request with the lower seq even
    when the capture lists it second."""
    _check(["h47", "h48"], "handling order")


def test_counter_wrap_is_reconstructed():
    """capture-format.md: a capture holds one unbroken run of a 16-bit counter,
    so 0 can follow 65535 and raw seq values are not positions."""
    _check(["h49", "h50"], "counter wrap")


def test_report_stays_in_file_order():
    """Spec 7.2: the report lists responses in the order the capture lists the
    requests, whatever order they were handled in."""
    _check(["h51"], "report order")


def test_fixture_state_evolves_in_counter_order():
    """Spec 5.4 and 7.1: which fixture answers next depends on how many requests
    the mock had already handled, not on how many the file had already listed."""
    _check(["h52"], "fixture state order")


# --------------------------------------------------------- the contract in force
def test_contract_in_force_is_the_one_at_the_request_counter():
    """capture-format.md `reloads` and reference/r03: a request is answered by
    the contract loaded when the mock handled it, so a route present only before
    a reload is a 404 after it and the other way round."""
    _check(["h53"], "contract in force")


def test_reload_selection_ignores_file_order():
    """reference/r04: the reload lines up with the request counter, not with the
    position of the request in the file, so a post-reload request written first
    still sees the new contract."""
    _check(["h54"], "reload selection")


def test_matched_is_indexed_against_the_live_contract():
    """Spec 6.2 and reference/r04: `matched` is an index into the route list in
    force for that request, so a route that moves across a reload reports a
    different index either side of it."""
    _check(["h55"], "matched index base")


def test_reload_replaces_the_route_list_outright():
    """reference/r05: a reload swaps the whole list, so its fixtures start unused
    and a limited fixture can answer again; and a reload can sit inside a run
    that wraps, or be followed by another."""
    _check(["h56", "h57", "h58"], "reload semantics")


# ------------------------------------------------------------------- HEAD
def test_head_is_answered_by_the_get_route():
    """reference/r06: a HEAD is a GET without a body, so a GET candidate answers
    it - chosen by the same precedence rule - and the fixture is consumed."""
    _check(["h59", "h60"], "implicit HEAD")


def test_declared_head_route_is_preferred():
    """reference/r07: a route declared for HEAD answers a HEAD request even when
    a GET route would otherwise have won on precedence."""
    _check(["h61"], "declared HEAD route")


def test_head_response_never_has_a_body():
    """reference/r06 and r08: every response to a HEAD carries a null body,
    whatever the status - a 404 for no route, a 400 refusal, a 404 for no
    matching fixture, and a 200."""
    _check(["h62", "h63"], "HEAD body")


def test_allow_header_lists_the_methods_answered():
    """Spec 2.3 and reference/r07: the allow header names the methods the
    candidates answer, sorted and joined with ", ", so a GET candidate puts HEAD
    in it and a declared HEAD route does not put it there twice."""
    _check(["h04", "h05", "h06", "h64"], "allow header")
