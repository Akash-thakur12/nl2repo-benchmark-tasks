"""Point-in-time feature pipeline for the churn model.

The pipeline answers one question for every labelled row: what did we know about
this customer on the day the prediction was made? Not what is true about that
day now, with the warehouse fully caught up - what had actually arrived by then.

Two timestamps do two different jobs, and they are not interchangeable:

  occurred_at   when the thing happened. This is what the lookback window means:
                "activity in the sixty days before the prediction".
  available_at  when the row reached the warehouse. This is what decides whether
                the row could have been used at all.

A row that happened inside the window but arrived after the cutoff is inside the
window and still unusable. Filtering on one timestamp and calling it done is the
mistake this pipeline exists to avoid.
"""
import collections
import csv
import datetime
import os
import pathlib

LOOKBACK_DAYS = 60

#: Feature order is fixed. The model is trained on positions, not names, so a
#: pipeline that emits the same numbers in a different order is a different
#: pipeline.
FEATURE_NAMES = ("login_count", "feature_used_count", "ticket_opened_count",
                 "seat_removed_count", "invoice_paid_count", "total_value")

_COUNTED = ("login", "feature_used", "ticket_opened", "seat_removed", "invoice_paid")


def _date(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d").date()


class PointInTimeEngine:
    """Builds features as of a date, and evaluates a model built from them."""

    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.environ.get("DATA_DIR") or (
                pathlib.Path(__file__).resolve().parent.parent / "data")
        self.data_dir = pathlib.Path(data_dir)
        self._events_by_customer = None
        self._labels = None

    # ---- loading -----------------------------------------------------------

    def _load(self):
        if self._events_by_customer is not None:
            return
        events = collections.defaultdict(list)
        with open(self.data_dir / "events.csv", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                events[row["customer_id"]].append({
                    "event_id": row["event_id"],
                    "customer_id": row["customer_id"],
                    "event_type": row["event_type"],
                    "occurred_at": _date(row["occurred_at"]),
                    "available_at": _date(row["available_at"]),
                    "revision": int(row["revision"]),
                    "value": float(row["value"]),
                })
        labels = []
        with open(self.data_dir / "labels.csv", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                labels.append({
                    "customer_id": row["customer_id"],
                    "as_of_date": _date(row["as_of_date"]),
                    "churned": int(row["churned"]),
                })
        self._events_by_customer = dict(events)
        self._labels = labels

    # ---- the point-in-time view -------------------------------------------

    def events_in_force(self, customer_id, as_of):
        """The rows this customer's record consisted of, as seen on `as_of`.

        Restatements share an event_id with the row they supersede and arrive
        later, so resolving them has to happen *after* the availability filter:
        a correction that had not yet landed does not apply, and the figure in
        force is the one from the newest revision that had.
        """
        self._load()
        cutoff = as_of if isinstance(as_of, datetime.date) else _date(as_of)

        in_force = {}
        for event in self._events_by_customer.get(customer_id, ()):
            if event["available_at"] > cutoff:
                continue                       # had not arrived yet
            best = in_force.get(event["event_id"])
            if best is None or event["revision"] > best["revision"]:
                in_force[event["event_id"]] = event
        return sorted(in_force.values(),
                      key=lambda e: (e["occurred_at"], e["event_id"]))

    def features(self, customer_id, as_of):
        """Feature vector for one prediction, as a name -> value mapping.

        The window is on when things happened; whether a row is visible at all
        is decided separately, by when it arrived.
        """
        cutoff = as_of if isinstance(as_of, datetime.date) else _date(as_of)
        window_start = cutoff - datetime.timedelta(days=LOOKBACK_DAYS)

        counts = collections.Counter()
        total_value = 0.0
        for event in self.events_in_force(customer_id, cutoff):
            if not (window_start < event["occurred_at"] <= cutoff):
                continue
            counts[event["event_type"]] += 1
            total_value += event["value"]

        vector = {name: float(counts[kind])
                  for name, kind in zip(FEATURE_NAMES, _COUNTED)}
        vector["total_value"] = round(total_value, 2)
        return vector

    def feature_row(self, customer_id, as_of):
        """The same vector as a list, in FEATURE_NAMES order."""
        vector = self.features(customer_id, as_of)
        return [vector[name] for name in FEATURE_NAMES]

    # ---- training and evaluation ------------------------------------------

    def training_frame(self, split_date):
        """(X_train, y_train, X_test, y_test), split by prediction date.

        The split is temporal because the question is whether the model works on
        dates it has not seen. A random split would put a customer's March row in
        training and their February row in test, which measures nothing.
        """
        self._load()
        boundary = split_date if isinstance(split_date, datetime.date) else _date(split_date)

        X_train, y_train, X_test, y_test = [], [], [], []
        for label in sorted(self._labels,
                            key=lambda r: (r["as_of_date"], r["customer_id"])):
            row = self.feature_row(label["customer_id"], label["as_of_date"])
            if label["as_of_date"] < boundary:
                X_train.append(row)
                y_train.append(label["churned"])
            else:
                X_test.append(row)
                y_test.append(label["churned"])
        return X_train, y_train, X_test, y_test

    def standardise(self, X_train, X_test):
        """Centre and scale, using statistics taken from the training rows only.

        The test rows are transformed with the training statistics rather than
        their own. Computing the mean over everything is the tidier-looking
        version and it is wrong: it carries the test distribution into the
        transform, so the reported score is no longer a statement about unseen
        data. A column with no spread is left alone rather than divided by zero.
        """
        columns = list(zip(*X_train)) if X_train else []
        means, scales = [], []
        for column in columns:
            mean = sum(column) / len(column)
            variance = sum((v - mean) ** 2 for v in column) / len(column)
            spread = variance ** 0.5
            means.append(mean)
            scales.append(spread if spread > 1e-12 else 1.0)

        def apply(rows):
            return [[(value - mean) / scale
                     for value, mean, scale in zip(row, means, scales)]
                    for row in rows]

        return apply(X_train), apply(X_test)

    def evaluate(self, split_date):
        """Fit on the earlier rows, score the later ones."""
        from engine.model import fit_logistic, predict_scores, roc_auc

        X_train, y_train, X_test, y_test = self.training_frame(split_date)
        if not X_train or not X_test:
            raise ValueError("split_date leaves one side of the split empty")

        X_train, X_test = self.standardise(X_train, X_test)
        weights, bias = fit_logistic(X_train, y_train)
        scores = predict_scores(X_test, weights, bias)
        return {
            "auc": float(roc_auc(scores, y_test)),
            "n_train": len(y_train),
            "n_test": len(y_test),
            "n_features": len(FEATURE_NAMES),
        }
