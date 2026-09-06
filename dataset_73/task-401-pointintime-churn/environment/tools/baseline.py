#!/usr/bin/env python3
"""The pipeline that produced the numbers in docs/RESULTS.md.

Kept for reference. Written against Revision B of the specification and never
brought up to Revision C.
"""
import collections
import csv
import datetime
import pathlib

LOOKBACK_DAYS = 60
FEATURES = ("login_count", "feature_used_count", "ticket_opened_count",
            "seat_removed_count", "invoice_paid_count", "total_value")
KINDS = ("login", "feature_used", "ticket_opened", "seat_removed", "invoice_paid")
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def date(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d").date()


def load():
    events = collections.defaultdict(list)
    for row in csv.DictReader(open(DATA / "events.csv", encoding="utf-8")):
        events[row["customer_id"]].append(row)
    labels = list(csv.DictReader(open(DATA / "labels.csv", encoding="utf-8")))
    return events, labels


def features(rows, as_of):
    """Everything the customer did in the window."""
    start = as_of - datetime.timedelta(days=LOOKBACK_DAYS)
    latest = {}
    for row in rows:
        if date(row["occurred_at"]) > as_of:
            continue
        seen = latest.get(row["event_id"])
        if seen is None or int(row["revision"]) > int(seen["revision"]):
            latest[row["event_id"]] = row

    counts = collections.Counter()
    total = 0.0
    for row in latest.values():
        if start < date(row["occurred_at"]) <= as_of:
            counts[row["event_type"]] += 1
            total += float(row["value"])
    return [float(counts[k]) for k in KINDS] + [round(total, 2)]


def main():
    events, labels = load()
    rows = [(features(events[r["customer_id"]], date(r["as_of_date"])),
             int(r["churned"]), date(r["as_of_date"])) for r in labels]
    print("%d rows, %d features" % (len(rows), len(FEATURES)))


if __name__ == "__main__":
    main()
