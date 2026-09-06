"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_flags.py over the held-out scenarios in /tests/scenarios, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
scenarios, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "scenarios")
REFERENCE = os.path.join(TESTS_DIR, "reference_flags.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="flags-verify-")
HELD_OUT = os.path.join(WORK, "scenarios")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_flags  # noqa: E402


def _expected(scenario_dir):
    if os.path.islink(scenario_dir):
        raise ValueError("scenario_dir cannot be a symlink")
    real_dir = os.path.realpath(scenario_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".scenario"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("scenario %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".scenario")]] = reference_flags.replay_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(scenario_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(scenario_dir), out_path],
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


def _field(entry, name):
    return entry.get(name) if isinstance(entry, dict) else None


def test_tool_runs_on_unseen_scenarios():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of scenarios it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per scenario, exactly the two documented
    keys per entry, each of the documented type."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "scenario keys differ"
    for name, want in EXPECTED.items():
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["evaluations", "flags"], "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["evaluations"], list), "%s: evaluations is not an array" % name
        assert isinstance(got["flags"], list), "%s: flags is not an array" % name
        for entry in got["evaluations"]:
            assert isinstance(entry, dict) and sorted(entry) == ["flag", "reason", "user", "variant"], \
                "%s: an evaluation must have exactly flag, user, variant and reason" % name


def test_evaluation_sequence_matches_specification():
    """Criterion 3: one entry per evaluate record, in order, naming the same
    flag and user."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = REPORT.get(name, {}).get("evaluations", [])
        if [(e["flag"], e["user"]) for e in want["evaluations"]] != \
           [(_field(e, "flag"), _field(e, "user")) for e in got]:
            wrong.append(name)
    assert not wrong, "evaluation sequence differs in: %s" % ", ".join(sorted(wrong))


def test_resolved_variants_match_specification():
    """Criterion 4: every evaluation resolves to the specified variant."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = REPORT.get(name, {}).get("evaluations", [])
        for i, expected_entry in enumerate(want["evaluations"]):
            actual = _field(got[i], "variant") if i < len(got) else None
            if actual != expected_entry["variant"]:
                wrong.append("%s[%d]" % (name, i))
    assert not wrong, "resolved variant differs in: %s" % ", ".join(wrong[:20])


def test_reasons_match_specification():
    """Criterion 5: every evaluation reports the specified reason."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = REPORT.get(name, {}).get("evaluations", [])
        for i, expected_entry in enumerate(want["evaluations"]):
            actual = _field(got[i], "reason") if i < len(got) else None
            if actual != expected_entry["reason"]:
                wrong.append("%s[%d]" % (name, i))
    assert not wrong, "reason differs in: %s" % ", ".join(wrong[:20])


def test_final_flag_set_matches_specification():
    """Criterion 6: the keys still defined when the scenario ended, sorted."""
    assert REPORT is not None, ERROR
    wrong = [name for name, want in EXPECTED.items()
             if REPORT.get(name, {}).get("flags") != want["flags"]]
    assert not wrong, "final flag set differs in: %s" % ", ".join(sorted(wrong))


def _compare(names, fields=("variant", "reason")):
    """Collect per-evaluation mismatches for a named subset of scenarios."""
    wrong = []
    for name in names:
        want = EXPECTED[name]["evaluations"]
        got = REPORT.get(name, {}).get("evaluations", []) if REPORT else []
        for i, expected_entry in enumerate(want):
            entry = got[i] if i < len(got) else None
            for field in fields:
                actual = _field(entry, field)
                if actual != expected_entry[field]:
                    wrong.append("%s[%d].%s = %r, expected %r"
                                 % (name, i, field, actual, expected_entry[field]))
    return wrong


def test_off_default_and_not_found_variants():
    """Criterion 4: a disabled flag serves off_variant, an undefined flag serves
    null, and a flag that matches nothing serves default_variant."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h01", "h02", "h19"], fields=("variant",))
    assert not wrong, "; ".join(wrong[:10])


def test_off_default_and_not_found_reasons():
    """Criterion 5: those three cases report OFF, FLAG_NOT_FOUND and DEFAULT."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h01", "h02", "h19"], fields=("reason",))
    assert not wrong, "; ".join(wrong[:10])


def test_rule_precedence_first_match_wins():
    """Criteria 4 and 5 (spec 2.4): the first matching rule wins and later
    matching rules are not consulted."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h06", "h24", "h25"])
    assert not wrong, "; ".join(wrong[:10])


def test_missing_attribute_never_matches():
    """Criteria 4 and 5 (spec 3.1): an absent attribute never matches, not even
    a not_in rule."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h07", "h23"])
    assert not wrong, "; ".join(wrong[:10])


def test_targeting_is_type_strict():
    """Criteria 4 and 5 (spec 3.3-3.5): exact type equality, string operators
    decline non-strings, and a bool is not a number."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h08", "h09", "h10", "h11", "h12", "h26", "h27", "h28"])
    assert not wrong, "; ".join(wrong[:10])


def test_prerequisites_are_evaluated_before_rules():
    """Criteria 4 and 5 (spec 2.3): prerequisites gate the evaluation, a failed
    one serves off_variant, and rules are not consulted first."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h03", "h20", "h22"])
    assert not wrong, "; ".join(wrong[:10])


def test_prerequisite_order_and_undefined_flags():
    """Criteria 4 and 5 (spec 2.3): every prerequisite is checked in order and a
    prerequisite naming an undefined flag is unsatisfied."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h04", "h21"])
    assert not wrong, "; ".join(wrong[:10])


def test_cycle_is_reported_by_the_entry_flag():
    """Criteria 4 and 5 (spec 5.1 / INC-4602 records (a) and (b)): a cycle
    anywhere in the chain aborts the evaluation and the entry flag reports its
    own off_variant with reason CYCLE."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h05", "h35"])
    assert not wrong, "; ".join(wrong[:10])


def test_cycle_is_not_masked_by_an_equal_prerequisite_variant():
    """Criteria 4 and 5 (spec 5.1 / INC-4602 record (c)): when the cycling
    flag's off_variant equals the variant its dependant required, the
    prerequisite must not be treated as satisfied."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h34", "h36"])
    assert not wrong, "; ".join(wrong[:10])


def test_bucketing_reproduces_the_service_assignments():
    """Criterion 4 (spec 4.1-4.4): rollout assignments match the reduction the
    service uses, per flag and per salt."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h13", "h14", "h15", "h16", "h29"], fields=("variant",))
    assert not wrong, "; ".join(wrong[:10])


def test_rollout_results_report_rule_rollout():
    """Criterion 5 (spec 2.4): a rollout result is reported as RULE_ROLLOUT, not
    RULE_MATCH."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h13", "h15", "h25"], fields=("reason",))
    assert not wrong, "; ".join(wrong[:10])


def test_bucketing_salt_is_pinned_across_updates():
    """Criterion 4 (spec 6.4 / CHANGELOG v3.0 INC-4471): the salt recorded when
    the key was created stays in force across later definitions."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h17", "h32"], fields=("variant",))
    assert not wrong, "; ".join(wrong[:10])


def test_deleting_a_flag_releases_its_bucketing_seed():
    """Criterion 4 (spec 6.4 / CHANGELOG v3.0 INC-4471): delete releases the
    seed, so a later definition of the same key allocates its own salt."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h33"], fields=("variant",))
    assert not wrong, "; ".join(wrong[:10])


def test_unallocated_rollout_falls_through_to_a_later_rule():
    """Criteria 4 and 5 (spec 4.3 / INC-4530): a bucket above the rollout total
    is not a rollout result, so a later matching rule still decides."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h30"])
    assert not wrong, "; ".join(wrong[:10])


def test_unallocated_rollout_falls_through_to_the_default():
    """Criteria 4 and 5 (spec 4.3 / INC-4530): with no later matching rule,
    unallocated traffic gets default_variant with reason DEFAULT."""
    assert REPORT is not None, ERROR
    wrong = _compare(["h31"])
    assert not wrong, "; ".join(wrong[:10])


def test_whole_report_matches_specification():
    """Criteria 2-6 together: the complete held-out report, exactly."""
    assert REPORT is not None, ERROR
    assert REPORT == EXPECTED, "the held-out report differs from the specification"


def test_sample_report_is_reproduced():
    """Criterion 7: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"
