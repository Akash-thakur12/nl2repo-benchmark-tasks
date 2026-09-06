# Churn model: point-in-time feature pipeline

We have a churn model. The offline numbers looked good enough to ship, so we
shipped it — and in production it performed nothing like the evaluation said it
would. The write-up we had been going on is in `docs/RESULTS.md`, and the code
that produced it is in `tools/baseline.py`.

Rebuild the pipeline so that its evaluation means something.

## What to build

`engine/engine.py`, a class `PointInTimeEngine` with these methods:

| method | returns |
|---|---|
| `events_in_force(customer_id, as_of)` | the customer's rows as seen on that date, ordered by `occurred_at` then `event_id` |
| `features(customer_id, as_of)` | feature name → value |
| `feature_row(customer_id, as_of)` | the same values as a list, in `FEATURE_NAMES` order |
| `standardise(X_train, X_test)` | both matrices, centred and scaled |
| `training_frame(split_date)` | `(X_train, y_train, X_test, y_test)` |
| `evaluate(split_date)` | `{"auc", "n_train", "n_test", "n_features"}` |

`events_in_force` returns dicts with keys `event_id`, `customer_id`,
`event_type`, `occurred_at`, `available_at`, `revision`, `value`; the two dates
are `datetime.date` objects.

`__init__(self, data_dir=None)` takes an optional data directory, falling back
to the `DATA_DIR` environment variable and then to `../data`.

## The rules

`docs/pipeline-spec.md` is normative and is the only current description of the
contract. Read it before writing anything: the parts that decide whether this
works are not the parts that look hardest.

`docs/CHANGELOG.md` says which revision is in force. Anything written under an
earlier revision is retained for audit and is not a specification.

## What is supplied

`engine/model.py` holds the optimiser and the metric. Both are deterministic.
Do not modify it — the graders import it. It is not what is being tested here;
the pipeline is.

Python standard library plus numpy. No network access.

## Done when

`pytest tests/test_outputs.py` passes in full.
