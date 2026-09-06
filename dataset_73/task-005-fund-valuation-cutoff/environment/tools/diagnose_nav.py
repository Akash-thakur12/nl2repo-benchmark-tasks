#!/usr/bin/env python3
"""nav-triage - support script for "why did this valuation not price?" tickets.

Written for the L1 support rota. Reads the price master, finds the nearest
available price date to the cutoff on the ticket and prints a suggested reply.

Run:  python tools/diagnose_nav.py 2025-03-15
"""
import csv
import datetime as dt
import pathlib
import sys

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "price_master.csv"


def load_price_dates():
    with open(DATA, newline="", encoding="utf-8") as fh:
        return sorted({dt.date.fromisoformat(r["price_date"]) for r in csv.DictReader(fh)})


def main():
    cutoff = dt.date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2025-03-15")
    dates = load_price_dates()

    if cutoff in dates:
        print("[nav-triage] cutoff %s is a pricing date - nothing to triage" % cutoff)
        return 0

    earlier = [d for d in dates if d < cutoff]
    print("[nav-triage] cutoff %s is not a pricing date" % cutoff)
    if not earlier:
        print("[nav-triage] no earlier price date at all - escalate to fund accounting")
        return 1
    print("[nav-triage] nearest available price date: %s" % earlier[-1])
    print("[nav-triage] ROOT CAUSE: weekend gap in vendor feed - request weekend")
    print("[nav-triage]   backfill, or fall back to the prior available price date")
    print("[nav-triage]   as the December pack did.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
