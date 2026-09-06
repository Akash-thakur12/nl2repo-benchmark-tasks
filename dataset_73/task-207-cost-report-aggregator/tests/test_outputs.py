"""Behaviour tests for /app/run.sh, one test per numbered success criterion.

Ground truth is derived here by running the reference model in
/tests/reference_chargeback.py over the held-out exports in /tests/exports, so no
expected value is hardcoded. Both are removed from disk before the candidate is
invoked, and the candidate runs from a scratch directory over a copy of the
exports, so it cannot read the answers out of /tests at verify time.

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
HELD_OUT_SRC = os.path.join(TESTS_DIR, "exports")
REFERENCE = os.path.join(TESTS_DIR, "reference_chargeback.py")
TOOL = "/app/run.sh"
SAMPLES = "/app/samples"

WORK = tempfile.mkdtemp(prefix="charge-verify-")
HELD_OUT = os.path.join(WORK, "exports")
shutil.copytree(HELD_OUT_SRC, HELD_OUT)

sys.path.insert(0, TESTS_DIR)
import reference_chargeback  # noqa: E402


def _expected(export_dir):
    if os.path.islink(export_dir):
        raise ValueError("export_dir cannot be a symlink")
    real_dir = os.path.realpath(export_dir)
    report = {}
    for name in sorted(os.listdir(real_dir)):
        if not name.endswith(".export"):
            continue
        path = os.path.join(real_dir, name)
        if os.path.islink(path):
            raise ValueError("scenario %s cannot be a symlink" % name)
        with open(os.path.realpath(path), encoding="utf-8") as handle:
            report[name[: -len(".export")]] = reference_chargeback.aggregate_text(handle.read())
    return report


EXPECTED = _expected(HELD_OUT)

for _leftover in (REFERENCE, HELD_OUT_SRC, os.path.join(TESTS_DIR, "__pycache__")):
    try:
        shutil.rmtree(_leftover) if os.path.isdir(_leftover) else os.remove(_leftover)
    except OSError:
        pass


def _run(export_dir, out_name):
    out_path = os.path.join(WORK, out_name)
    if os.path.islink(TOOL):
        return None, "%s must not be a symlink" % TOOL
    if not os.access(TOOL, os.X_OK):
        return None, "%s is not executable" % TOOL
    proc = subprocess.run([os.path.realpath(TOOL), os.path.realpath(export_dir), out_path],
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


def _compare_group(names, label):
    """Compare whole report entries for one group of exports.

    Group tests are what makes the score continuous: understanding one mechanism
    earns its test immediately, without having to get every other mechanism right
    first, while the all-export comparisons above stay as the top of the ladder.
    """
    assert REPORT is not None, ERROR
    missing = [n for n in names if n not in EXPECTED]
    assert not missing, "the held-out corpus is missing: %s" % ", ".join(missing)
    wrong = [n for n in names if REPORT.get(n) != EXPECTED[n]]
    assert not wrong, "%s differs from the specification in: %s" % (
        label, ", ".join(sorted(wrong)))


def test_tool_runs_on_unseen_exports():
    """Criterion 1: /app/run.sh exists, is executable, and completes on a
    directory of exports it has not seen before."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    assert REPORT is not None, ERROR


def test_report_shape_is_correct():
    """Criterion 2: valid JSON, one key per export, exactly the four documented
    keys per entry, with one team row per configured team."""
    assert REPORT is not None, ERROR
    assert sorted(REPORT) == sorted(EXPECTED), "export keys differ"
    row_fields = ["amortised", "credit", "shared", "total", "usage"]
    for name, want in EXPECTED.items():
        got = REPORT[name]
        assert isinstance(got, dict), "%s: entry is not an object" % name
        assert sorted(got) == ["errors", "teams", "unallocated", "unused_credit"],             "%s: wrong keys %s" % (name, sorted(got))
        assert isinstance(got["teams"], dict), "%s: teams is not an object" % name
        assert sorted(got["teams"]) == sorted(want["teams"]),             "%s: team keys differ" % name
        for team, row in got["teams"].items():
            assert isinstance(row, dict) and sorted(row) == row_fields,                 "%s/%s: a team row must have exactly %s" % (name, team, row_fields)
            for field in row_fields:
                assert isinstance(row[field], int) and not isinstance(row[field], bool),                     "%s/%s/%s: not an integer" % (name, team, field)
        for field in ("unallocated", "unused_credit"):
            assert isinstance(got[field], int) and not isinstance(got[field], bool),                 "%s: %s is not an integer" % (name, field)
        assert isinstance(got["errors"], list), "%s: errors is not an array" % name
        for entry in got["errors"]:
            assert isinstance(entry, dict) and sorted(entry) == ["code", "detail"],                 "%s: an error must have exactly code and detail" % name


def test_team_rows_match():
    """Criterion 3: usage, amortised, shared, credit and total for every team."""
    _compare("teams", "team rows")


def test_unallocated_matches():
    """Criterion 4: money that reached no team, including untagged usage and
    shared costs with nothing to split across."""
    _compare("unallocated", "unallocated")


def test_unused_credit_matches():
    """Criterion 5: credit that could not be applied."""
    _compare("unused_credit", "unused credit")


def test_errors_match():
    """Criterion 6: duplicate line ids and unknown teams, in line order."""
    _compare("errors", "errors")


def test_totals_reconcile():
    """Criterion 7: every team's total plus unallocated equals what was charged
    inside the period, less the credit actually applied."""
    assert REPORT is not None, ERROR
    wrong = []
    for name, want in EXPECTED.items():
        got = REPORT.get(name, {})
        rows = got.get("teams", {})
        charged = sum(r["usage"] + r["amortised"] + r["shared"] for r in rows.values())
        credited = sum(r["credit"] for r in rows.values())
        totals = sum(r["total"] for r in rows.values())
        if totals != charged - credited:
            wrong.append(name + " (team totals)")
        elif got.get("unallocated") != want["unallocated"]:
            wrong.append(name + " (unallocated)")
    assert not wrong, "totals do not reconcile in: %s" % ", ".join(sorted(wrong))


def test_sample_report_is_reproduced():
    """Criterion 8: running the tool on /app/samples reproduces expected.json."""
    assert os.path.exists(TOOL), "%s is missing" % TOOL
    report, error = _run(SAMPLES, "samples.json")
    assert report is not None, error
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        assert report == json.load(handle), "sample report does not match expected.json"


# --------------------------------------------------------------- group tests
# One mechanism per test, so a partially correct implementation scores
# partially. Every export named here is also covered by the all-export
# comparisons above.


def test_shared_remainder_order():
    """Section 5.2: the shared remainder is handed out in descending weight,
    ties broken by ascending team name, wrapping when it runs out of teams."""
    _compare_group(["h01", "h02", "h03", "h04", "h05", "h06", "h36", "h37"],
                   "the shared remainder order")


def test_zero_and_absent_weights():
    """Sections 5.3-5.5: a zero weight takes nothing, weights totalling zero
    send the line to unallocated, and a weight for a team the report does not
    cover neither counts nor is an error."""
    _compare_group(["h07", "h08", "h09", "h10", "h11"], "zero and absent weights")


def test_reservation_amortisation():
    """Sections 4.1-4.5: the daily amount, the remainder on the earliest days of
    the term, and only the days of the term inside the period."""
    _compare_group(["h12", "h13", "h14", "h15", "h16", "h17", "h18", "h19",
                    "h20", "h38", "h39"], "reservation amortisation")


def test_period_filtering():
    """Sections 1.2 and 4.5: a line dated outside the period contributes nothing
    and is not an error, but a reservation is not day-gated."""
    _compare_group(["h21", "h22"], "period filtering")


def test_untagged_duplicates_and_unknown_teams():
    """Sections 2.2, 2.3 and 3.2: untagged usage is unallocated, the first line
    with an id stands, and an unknown team is recorded rather than dropped
    silently."""
    _compare_group(["h23", "h24", "h25", "h26", "h27"],
                   "untagged usage, duplicates and unknown teams")


def test_credits_settle_after_charges():
    """Sections 6.1-6.4: credits settle after every charge is totalled, in line
    order, clamped at zero, with the residue in unused_credit."""
    _compare_group(["h28", "h29", "h30", "h31", "h32"], "credit settlement")


def test_every_configured_team_has_a_row():
    """Section 7.1: a team with nothing charged still gets a row."""
    _compare_group(["h33", "h34"], "rows for teams with nothing charged")


def test_weight_amendment_applies_from_its_own_day():
    """Section 5.1 and the reconciliation memo: a `weight_changes` entry replaces
    `shared_weights` from its own `day` onward, and the amendment day itself is
    already on the new split. Lines before it keep the opening configuration."""
    _compare_group(["w01", "w02"], "the day a weight amendment takes effect")


def test_weight_amendment_selected_by_day_not_position():
    """The memo's amendment table: the array is in filing order, not day order,
    so the amendment in force is the latest-dated one on or before the line's
    day, a later entry wins a shared day, and an amendment dated after the
    period never applies."""
    _compare_group(["w03", "w06", "w07", "w08"], "amendment selection")


def test_amendment_that_zeroes_the_split():
    """Sections 5.3-5.5 under an amendment: an amendment may zero every weight or
    supply none at all, sending later shared lines to unallocated while earlier
    ones still split, and may carry zero and unlisted-team weights."""
    _compare_group(["w04", "w05", "w09"], "an amendment that zeroes the split")


def test_amendments_do_not_touch_other_line_kinds():
    """Section 5 is confined to shared lines: usage, reservations and credits are
    unaffected by a weight amendment."""
    _compare_group(["w10"], "amendments against other line kinds")


def test_retired_name_charges_its_successor():
    """Section 2.4 and the memo: a line carrying a retired team name charges the
    team it became, on usage, reservation and credit lines alike, and is not an
    error."""
    _compare_group(["n01", "n02", "n07"], "retired names on lines")


def test_retired_weight_folds_into_successor():
    """The memo's R-2: a weight filed under a retired name is the successor's
    weight, added to any weight the successor already has, and so does raise the
    total weight - unlike a weight naming a team the report does not cover."""
    _compare_group(["n03", "n04", "n09"], "retired weight keys")


def test_remainder_tie_break_uses_the_canonical_name():
    """The memo's R-3: section 5.2 breaks a weight tie on the name the report
    bills under, not on the weight key as written."""
    _compare_group(["n05"], "the canonical-name tie-break")


def test_unresolvable_name_is_still_an_unknown_team():
    """The memo's R-4: a retired name whose successor the report does not cover
    is still UNKNOWN_TEAM under section 2.3, reported under the name the line
    carries; the same weight key is struck out without an error."""
    _compare_group(["n06", "n08"], "unresolvable retired names")


def test_amendments_and_renames_together():
    """Sections 2.4 and 5.1 interacting: amendment weight maps keyed by retired
    names, a zeroing amendment beside a retired name on a reservation, untagged
    usage, a duplicate and a clamped credit in one export."""
    _compare_group(["x01", "x02", "x03"], "amendments and renames together")
