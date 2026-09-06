#!/usr/bin/env python3
"""Generate the event log and label table for the point-in-time task.

The whole task turns on one property of the data, so it is worth stating plainly
here: an event carries two timestamps. `occurred_at` is when the thing happened.
`available_at` is when it landed in the warehouse, which is later, because the
upstream systems deliver in batches and some of them are slow.

A prediction made on a given day can only have used rows that had arrived by
that day. Filtering on `occurred_at` instead admits rows the model could not
have seen, and because those rows are precisely the ones that describe what the
customer did just before churning, the leak flatters the score rather than
hurting it. That is what makes it dangerous: the wrong pipeline looks better.

Corrections work the same way. A restated row shares its `event_id` with the row
it supersedes and arrives later; only the latest restatement that had arrived by
the cutoff counts.

The generator is seeded, so the shipped CSVs are reproducible from this file.
"""
import csv
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parent / "environment" / "data"

DAY = 86400
ORIGIN = 1735689600            # 2025-01-01T00:00:00Z, kept as an epoch second
                               # so nothing depends on a timezone database.
EVENT_TYPES = ["login", "ticket_opened", "invoice_paid", "seat_removed", "feature_used"]

# Delivery lag per source, in days. login is streamed and lands the same day;
# billing is a nightly batch; the support system is reconciled weekly, which is
# where most of the damage lives.
LAG = {"login": 0, "feature_used": 0, "invoice_paid": 2, "ticket_opened": 7,
       "seat_removed": 7}


def iso(epoch):
    """Epoch second -> 'YYYY-MM-DD'. Deliberately date-granular."""
    import datetime
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%d")


def main():
    rng = random.Random(20260907)
    DATA.mkdir(parents=True, exist_ok=True)

    events, labels = [], []
    event_id = 0

    for customer in range(1, 241):
        cid = "C%04d" % customer
        # Churn risk is what the features should be able to see - but only
        # through rows that had actually arrived.
        churn_day = rng.randint(150, 300) if rng.random() < 0.42 else None
        base_rate = rng.uniform(0.25, 1.6)

        for day in range(0, 330):
            when = ORIGIN + day * DAY
            # Activity decays in the run-up to a churn, and support contact and
            # seat removals spike. Both of those are the slow-arriving sources.
            near_churn = churn_day is not None and 0 <= churn_day - day <= 45
            rate = base_rate * (0.35 if near_churn else 1.0)

            for _ in range(1 if rng.random() < rate / 2 else 0):
                kind = "login" if rng.random() < 0.7 else "feature_used"
                event_id += 1
                events.append([("E%06d" % event_id), cid, kind, iso(when),
                               iso(when + LAG[kind] * DAY), 1, "%.2f" % rng.uniform(1, 5)])

            if near_churn and rng.random() < 0.30:
                kind = "ticket_opened" if rng.random() < 0.6 else "seat_removed"
                event_id += 1
                events.append([("E%06d" % event_id), cid, kind, iso(when),
                               iso(when + LAG[kind] * DAY), 1, "%.2f" % rng.uniform(1, 9)])

            if rng.random() < 0.02:
                event_id += 1
                events.append([("E%06d" % event_id), cid, "invoice_paid", iso(when),
                               iso(when + LAG["invoice_paid"] * DAY), 1,
                               "%.2f" % rng.uniform(50, 400)])

        # Prediction points, every 30 days. The label is whether the customer
        # churned within the 30 days that follow.
        for day in range(90, 300, 30):
            churned = int(churn_day is not None and day < churn_day <= day + 30)
            labels.append([cid, iso(ORIGIN + day * DAY), churned])

    # Restatements: a later row supersedes an earlier one under the same
    # event_id. revision counts up; only the newest revision that had arrived by
    # the cutoff is in force.
    corrections = []
    for row in rng.sample(events, 260):
        occurred = row[3]
        import datetime
        arrive = (datetime.datetime.strptime(occurred, "%Y-%m-%d")
                  + datetime.timedelta(days=rng.randint(9, 40)))
        corrections.append([row[0], row[1], row[2], occurred,
                            arrive.strftime("%Y-%m-%d"), 2,
                            "%.2f" % (float(row[6]) * rng.uniform(1.4, 2.6))])
    events.extend(corrections)

    # Shipped in arrival order rather than sorted by anything useful, which is
    # how a warehouse dump actually looks.
    rng.shuffle(events)

    with open(DATA / "events.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["event_id", "customer_id", "event_type", "occurred_at",
                    "available_at", "revision", "value"])
        w.writerows(events)

    labels.sort()
    with open(DATA / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["customer_id", "as_of_date", "churned"])
        w.writerows(labels)

    late = sum(1 for e in events if e[4] != e[3])
    print("events      %d  (%d arrive later than they occurred)" % (len(events), late))
    print("corrections %d" % len(corrections))
    print("labels      %d  (%d positive)" % (len(labels), sum(r[2] for r in labels)))


if __name__ == "__main__":
    main()
