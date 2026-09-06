#!/usr/bin/env python3
"""rollover_diag -- field diagnostic for week-rollover complaints.

Reads ../samples/decoded_frames.jsonl, re-decodes every frame with the AN-0417
repair logic, and compares the calendar date against the date recorded in the
corpus. Sub-day discrepancies are not checked; the field complaint this tool was
written for was always "wrong day", never "wrong second".

  python3 rollover_diag.py

Stdlib only. Runs on the 3.2.1 recovery image.
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, os.pardir, "samples", "decoded_frames.jsonl")

# AN-0417 s4 anchors.
ANCHORS = [
    (0, dt.date(1999, 8, 22)),
    (1024, dt.date(2019, 4, 7)),
    (2048, dt.date(2038, 11, 21)),
]

# AN-0417 s2.1: the count is this subframe's own time, in six-second units.
SUBFRAME_SECONDS = 6
# AN-0417 s3: a single constant is sufficient.
GPS_UTC_OFFSET = 18

WEEK_EPOCH = {
    "lnav": dt.date(1999, 8, 22),
    "cnav": dt.date(1999, 8, 22),
    "almanac": dt.date(1999, 8, 22),
    "bdt": dt.date(2006, 1, 1),
}
ABSOLUTE = {"cnav", "bdt"}


def resolve_week(raw, source, ref):
    """AN-0417 s4/s5: most recent anchor not later than the reference date."""
    if source in ABSOLUTE:
        return raw
    candidates = [(b, a) for b, a in ANCHORS if a <= ref]
    if not candidates:
        candidates = [ANCHORS[0]]
    base, _anchor = candidates[-1]
    return base + ((raw - base) % 1024)


def repair(row):
    """Re-decode one frame the way AN-0417 says to."""
    ref = dt.date.fromisoformat(row["ref"])
    source = row["source"]
    week = resolve_week(row["raw_week"], source, ref)
    epoch = WEEK_EPOCH[source]
    instant = (dt.datetime(epoch.year, epoch.month, epoch.day)
               + dt.timedelta(weeks=week, seconds=row["tow_count"] * SUBFRAME_SECONDS))
    return instant - dt.timedelta(seconds=GPS_UTC_OFFSET)


def main():
    with open(CORPUS) as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    explained = 0
    unexplained = []
    for row in rows:
        want = dt.datetime.fromisoformat(row["expected_utc"])
        got = repair(row)
        if got.date() == want.date():
            explained += 1
            status = "ok  "
        else:
            unexplained.append(row["id"])
            status = "BAD "
        print("%s %s %-8s raw_week=%-5d tow=%-6d expected=%s repaired=%s"
              % (status, row["id"], row["source"], row["raw_week"],
                 row["tow_count"], want.isoformat(), got.isoformat()))

    print()
    print("%d of %d frames resolve to the correct calendar date." % (explained, len(rows)))
    print()
    print("ROOT CAUSE (AN-0417 s4): the 1024-week modulus is applied after the")
    print("reference comparison. Fix: resolve every raw week against the MOST")
    print("RECENT anchor whose date does not exceed the reference date.")
    print()
    print("%d frames unexplained -- see AN-0611: %s"
          % (len(unexplained), ", ".join(unexplained)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
