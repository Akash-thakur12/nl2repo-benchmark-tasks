"""Behaviour tests, one per rule in docs/pipeline-spec.md.

Each test names the section it enforces. They are independent, so a pipeline
that gets some rules right and others wrong scores in between rather than
failing outright.
"""
import datetime

import pytest

from engine.engine import FEATURE_NAMES, LOOKBACK_DAYS, PointInTimeEngine
from engine.model import fit_logistic, predict_scores, roc_auc


def d(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d").date()


@pytest.fixture(scope="module")
def engine():
    return PointInTimeEngine()


# --- section 2, 4: what the record consisted of on a given day --------------

def test_a_row_that_has_not_arrived_is_not_in_force(engine):
    """Section 2. E000681 occurred on 2025-08-25 but reached the warehouse on
    2025-09-01, so a prediction made on 2025-08-29 could not have used it."""
    ids = {e["event_id"] for e in engine.events_in_force("C0004", "2025-08-29")}
    assert "E000681" not in ids


def test_the_same_row_is_in_force_once_it_has_arrived(engine):
    """Section 2. The same event is usable on 2025-09-01, the day it landed."""
    ids = {e["event_id"] for e in engine.events_in_force("C0004", "2025-09-01")}
    assert "E000681" in ids


def test_availability_is_judged_on_the_day_itself(engine):
    """Section 2. Arrival on the cutoff date counts: the bound is inclusive."""
    before = {e["event_id"] for e in engine.events_in_force("C0004", "2025-08-31")}
    on_the_day = {e["event_id"] for e in engine.events_in_force("C0004", "2025-09-01")}
    assert "E000681" not in before
    assert "E000681" in on_the_day


def test_an_old_row_that_has_arrived_is_in_force(engine):
    """Section 2. Nothing ages out of the record; only the window is bounded."""
    rows = engine.events_in_force("C0001", "2025-09-01")
    assert any(e["occurred_at"] < d("2025-03-01") for e in rows)


def test_a_restatement_supersedes_the_row_it_restates(engine):
    """Section 4. E000332 was restated from 1.61 to 4.16; the restatement had
    arrived by 2025-06-10, so 4.16 is the figure in force."""
    rows = {e["event_id"]: e for e in engine.events_in_force("C0002", "2025-06-10")}
    assert rows["E000332"]["value"] == pytest.approx(4.16)
    assert rows["E000332"]["revision"] == 2


def test_a_restatement_that_has_not_arrived_does_not_apply(engine):
    """Section 4. On 2025-05-25 the restatement had not landed, so the original
    1.61 still stands. Resolving revisions before filtering on arrival gets this
    wrong."""
    rows = {e["event_id"]: e for e in engine.events_in_force("C0002", "2025-05-25")}
    assert rows["E000332"]["value"] == pytest.approx(1.61)
    assert rows["E000332"]["revision"] == 1


def test_each_event_appears_once(engine):
    """Section 4. A restated event contributes one row, not one per revision."""
    rows = engine.events_in_force("C0002", "2025-09-01")
    ids = [e["event_id"] for e in rows]
    assert len(ids) == len(set(ids))


def test_rows_are_ordered_by_occurrence(engine):
    """Section 2. The shipped file is in arrival order; the output is not."""
    rows = engine.events_in_force("C0001", "2025-07-01")
    keys = [(e["occurred_at"], e["event_id"]) for e in rows]
    assert keys == sorted(keys)


def test_rows_carry_dates_as_date_objects(engine):
    """Contract in instruction.md: both timestamps are datetime.date."""
    row = engine.events_in_force("C0001", "2025-07-01")[0]
    assert isinstance(row["occurred_at"], datetime.date)
    assert isinstance(row["available_at"], datetime.date)


# --- section 5: features ---------------------------------------------------

def test_features_exclude_support_rows_that_had_not_arrived(engine):
    """Section 5 with 2. C0004 has tickets and a seat removal inside the window
    on 2025-08-29, all still in the weekly support extract. A pipeline that
    windows on occurrence alone reports 2 and 1 here instead of nothing."""
    vector = engine.features("C0004", "2025-08-29")
    assert vector["ticket_opened_count"] == 0.0
    assert vector["seat_removed_count"] == 0.0


def test_features_match_the_record_as_of_the_date(engine):
    """Section 5. Full vector for C0004 on 2025-08-29."""
    assert engine.features("C0004", "2025-08-29") == {
        "login_count": 21.0, "feature_used_count": 13.0,
        "ticket_opened_count": 0.0, "seat_removed_count": 0.0,
        "invoice_paid_count": 3.0, "total_value": 770.4,
    }


def test_a_late_invoice_does_not_count_early(engine):
    """Section 5 with 2. Billing is a nightly batch, so an invoice paid close to
    the cutoff has not landed. C0002 shows one invoice on 2025-08-29, not two."""
    assert engine.features("C0002", "2025-08-29")["invoice_paid_count"] == 1.0


def test_total_value_reflects_the_revision_in_force(engine):
    """Section 4 with 5. C0001's window on 2025-05-31 sums to 421.59; using
    restated figures that had not yet arrived gives a larger number."""
    assert engine.features("C0001", "2025-05-31")["total_value"] == pytest.approx(421.59)


def test_total_value_is_rounded_to_two_decimals(engine):
    """Section 5."""
    value = engine.features("C0001", "2025-06-30")["total_value"]
    assert value == round(value, 2)


def test_the_window_excludes_its_own_left_edge(engine):
    """Section 5. The interval is (as_of - 60, as_of], so an event exactly
    sixty days back is out and the counts equal the rows strictly inside."""
    as_of = d("2025-08-29")
    edge = as_of - datetime.timedelta(days=LOOKBACK_DAYS)
    inside = [e for e in engine.events_in_force("C0001", as_of)
              if edge < e["occurred_at"] <= as_of]
    vector = engine.features("C0001", as_of)
    assert sum(vector[n] for n in FEATURE_NAMES[:5]) == len(inside)


def test_the_window_closes_on_the_as_of_date(engine):
    """Section 5. The upper bound is inclusive. C0001 has an event on
    2025-05-31 itself, so an exclusive bound reports 45 here instead of 46."""
    vector = engine.features("C0001", "2025-05-31")
    assert sum(vector[n] for n in FEATURE_NAMES[:5]) == 46.0


def test_feature_row_follows_the_declared_order(engine):
    """Section 5. The model is trained on positions, so order is contractual."""
    vector = engine.features("C0004", "2025-08-29")
    assert engine.feature_row("C0004", "2025-08-29") == [vector[n] for n in FEATURE_NAMES]


# --- section 6: the split --------------------------------------------------

def test_the_split_is_by_date_not_by_row(engine):
    """Section 6. Sizes at the 2025-08-01 boundary."""
    X_train, y_train, X_test, y_test = engine.training_frame("2025-08-01")
    assert len(X_train) == len(y_train) == 1200
    assert len(X_test) == len(y_test) == 480


def test_moving_the_boundary_moves_rows_across_it(engine):
    """Section 6. A later boundary means more training rows, fewer test rows."""
    early = engine.training_frame("2025-07-01")
    late = engine.training_frame("2025-09-01")
    assert len(early[0]) < len(late[0])
    assert len(early[2]) > len(late[2])


def test_every_labelled_row_is_used_exactly_once(engine):
    """Section 6. The split partitions the labels; nothing is dropped."""
    X_train, y_train, X_test, y_test = engine.training_frame("2025-08-01")
    assert len(y_train) + len(y_test) == 1680


# --- section 7: standardisation --------------------------------------------

def test_standardisation_centres_the_training_columns(engine):
    """Section 7. Training columns come out with mean zero."""
    X_train, _, X_test, _ = engine.training_frame("2025-08-01")
    scaled_train, _ = engine.standardise(X_train, X_test)
    for column in zip(*scaled_train):
        assert sum(column) / len(column) == pytest.approx(0.0, abs=1e-9)


def test_standardisation_uses_training_statistics_for_the_test_rows(engine):
    """Section 7. The test columns are transformed with the training mean and
    spread, so they do not come out centred themselves. Fitting the transform on
    everything is the leak this rule exists to stop."""
    X_train, _, X_test, _ = engine.training_frame("2025-08-01")
    _, scaled_test = engine.standardise(X_train, X_test)
    means = [sum(column) / len(column) for column in zip(*scaled_test)]
    assert any(abs(mean) > 1e-6 for mean in means)


def test_standardisation_uses_the_population_deviation(engine):
    """Section 7. Divided by n, not n - 1."""
    scaled_train, _ = engine.standardise([[0.0], [2.0], [4.0], [6.0]], [[0.0]])
    assert scaled_train[0][0] == pytest.approx(-1.3416407865, rel=1e-9)


def test_a_constant_column_survives_standardisation(engine):
    """Section 7. Zero spread is left alone rather than dividing by zero."""
    scaled_train, scaled_test = engine.standardise([[5.0], [5.0], [5.0]], [[9.0]])
    assert all(row[0] == pytest.approx(0.0) for row in scaled_train)
    assert scaled_test[0][0] == pytest.approx(4.0)


# --- section 8: evaluation -------------------------------------------------

def test_evaluate_reports_the_score_of_the_point_in_time_pipeline(engine):
    """Section 8. The honest number for a split at 2025-08-01. A pipeline that
    lets unarrived rows through scores materially higher than this."""
    assert engine.evaluate("2025-08-01")["auc"] == pytest.approx(0.882370283, abs=1e-6)


def test_evaluate_reports_the_score_at_a_second_boundary(engine):
    """Section 8. Holding at one split could be luck; this one differs in size."""
    assert engine.evaluate("2025-07-01")["auc"] == pytest.approx(0.8854166667, abs=1e-6)


def test_evaluate_reports_the_shape_of_the_problem(engine):
    """Section 8."""
    result = engine.evaluate("2025-08-01")
    assert result["n_train"] == 1200
    assert result["n_test"] == 480
    assert result["n_features"] == 6


def test_evaluate_is_deterministic(engine):
    """Section 8. Same rows in, same number out - the optimiser never samples."""
    assert engine.evaluate("2025-08-01")["auc"] == engine.evaluate("2025-08-01")["auc"]


def test_evaluate_refuses_a_split_with_nothing_on_one_side(engine):
    """Section 8. A boundary outside the data is a mistake, not a score, and
    it is reported as a ValueError rather than any exception that happens to
    escape."""
    with pytest.raises(ValueError):
        engine.evaluate("2024-01-01")


def test_the_supplied_metric_is_used_unmodified(engine):
    """Section 8. Rebuilding the evaluation by hand from the pipeline's own
    frame reproduces what evaluate() reports."""
    X_train, y_train, X_test, y_test = engine.training_frame("2025-08-01")
    X_train, X_test = engine.standardise(X_train, X_test)
    weights, bias = fit_logistic(X_train, y_train)
    expected = roc_auc(predict_scores(X_test, weights, bias), y_test)
    assert engine.evaluate("2025-08-01")["auc"] == pytest.approx(expected, abs=1e-12)


def test_the_boundary_date_itself_belongs_to_the_test_side(engine):
    """Section 6. The comparison is strict: rows dated exactly on `split_date`
    are test rows, not training rows. 2025-07-30 is one of the seven prediction
    dates, so an inclusive comparison moves 240 rows across the boundary."""
    X_train, y_train, X_test, y_test = engine.training_frame("2025-07-30")
    assert len(y_train) == 960
    assert len(y_test) == 720


def test_evaluate_refuses_a_split_that_leaves_no_test_rows(engine):
    """Section 8. Either side being empty is the error, not both. A boundary
    after the last prediction date leaves nothing to score."""
    with pytest.raises(ValueError):
        engine.evaluate("2026-01-01")
