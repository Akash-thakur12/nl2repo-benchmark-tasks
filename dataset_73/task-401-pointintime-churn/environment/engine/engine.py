"""Point-in-time feature pipeline for the churn model.

Implement the methods below. The contract is in docs/pipeline-spec.md, which is
normative; where this file's comments and that document disagree, the document
wins.

engine/model.py is supplied and must not be modified.
"""
import os
import pathlib

LOOKBACK_DAYS = 60

FEATURE_NAMES = ("login_count", "feature_used_count", "ticket_opened_count",
                 "seat_removed_count", "invoice_paid_count", "total_value")


class PointInTimeEngine:
    """Builds features as of a date, and evaluates a model built from them."""

    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.environ.get("DATA_DIR") or (
                pathlib.Path(__file__).resolve().parent.parent / "data")
        self.data_dir = pathlib.Path(data_dir)

    def events_in_force(self, customer_id, as_of):
        """The rows this customer's record consisted of, as seen on `as_of`.

        Returns a list of dicts with keys event_id, customer_id, event_type,
        occurred_at, available_at, revision and value. Dates are datetime.date.
        Ordered by occurred_at, then event_id.
        """
        raise NotImplementedError

    def features(self, customer_id, as_of):
        """Feature vector for one prediction, as a name -> value mapping."""
        raise NotImplementedError

    def feature_row(self, customer_id, as_of):
        """The same vector as a list, in FEATURE_NAMES order."""
        raise NotImplementedError

    def standardise(self, X_train, X_test):
        """Centre and scale both matrices. Returns (X_train, X_test)."""
        raise NotImplementedError

    def training_frame(self, split_date):
        """(X_train, y_train, X_test, y_test)."""
        raise NotImplementedError

    def evaluate(self, split_date):
        """{"auc": float, "n_train": int, "n_test": int, "n_features": int}."""
        raise NotImplementedError
