# Churn feature pipeline — specification

Revision C, in force. Supersedes Revision B (see CHANGELOG.md).

## 1. What the model is for

For a given customer and a given date, predict whether that customer will churn
within the next thirty days. The prediction is made *on* that date. Everything
the pipeline computes must therefore be something the business actually knew on
that date.

## 2. The event log

`data/events.csv`, one row per event, in warehouse arrival order — it is not
sorted, and nothing downstream may assume it is.

| column | meaning |
|---|---|
| `event_id` | identifies the event. Not unique across rows: see §4. |
| `customer_id` | |
| `event_type` | one of `login`, `feature_used`, `ticket_opened`, `seat_removed`, `invoice_paid` |
| `occurred_at` | the date the event happened |
| `available_at` | the date the row reached the warehouse |
| `revision` | see §4 |
| `value` | amount attached to the event |

`available_at` is never earlier than `occurred_at`, and for several sources it is
materially later. Logins and feature use are streamed and arrive the same day.
Billing is a nightly batch. The support system — tickets and seat changes — is
reconciled on a weekly cycle.

## 3. The labels

`data/labels.csv` gives the prediction points: a customer, an `as_of_date`, and
`churned`, which is 1 if that customer churned in the thirty days after the
as-of date.

## 4. Restatements

An event can be restated. A restatement carries the same `event_id`, a higher
`revision`, and its own `available_at`, which is later than the original's. It
supersedes what came before it.

The figure in force for an event, on a given date, is the one from the highest
revision that had arrived by that date. A restatement that had not yet arrived
has not happened yet, as far as that date is concerned.

## 5. Features

Six features, in this order:

    login_count, feature_used_count, ticket_opened_count,
    seat_removed_count, invoice_paid_count, total_value

The first five count events of that type. `total_value` sums `value` across all
events, rounded to two decimals.

All six are computed over a **sixty-day lookback window** ending at the as-of
date: events with `occurred_at` in the half-open interval
`(as_of − 60 days, as_of]`.

The window is about when things happened. Whether a row may be used at all is a
separate question, answered by §2 and §4.

## 6. The split

`training_frame(split_date)` divides the labelled rows by their `as_of_date`:
strictly earlier than `split_date` is training, the rest is test. Rows are
ordered by `as_of_date`, then `customer_id`.

The split is by date because the question being asked is whether the model works
on dates it has not seen.

## 7. Standardisation

Before fitting, each feature column is centred and scaled. The mean and standard
deviation come from the **training rows only**, and the same transform is then
applied to both sides. A column whose standard deviation is zero is left
uncentred and unscaled rather than divided by zero.

Standard deviation is the population form, dividing by *n*.

## 8. Model and metric

`engine/model.py` is supplied and must not be modified. `fit_logistic` is
full-batch, starts at zero, and takes a fixed number of steps, so it is
deterministic. `roc_auc` averages the ranks of tied scores.

`evaluate(split_date)` fits on the training rows, scores the test rows, and
returns `auc`, `n_train`, `n_test` and `n_features`.

A `split_date` that leaves either side of the split empty raises `ValueError`.
An empty side is a mistake in the caller, not a model that scored badly.
