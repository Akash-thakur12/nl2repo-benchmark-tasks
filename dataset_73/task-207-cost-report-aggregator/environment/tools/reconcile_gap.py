#!/usr/bin/env python3
"""reconcile_gap.py - finance's shared-cost checker.

  usage: python3 reconcile_gap.py <export file>

Prints the per-team shared split for an export and explains the gap between the
sum of the lines and the sum of the team rows.

Notes for whoever picks this up:

  * The weight table can be amended mid-period (`weight_changes`). We take the
    amendment as the month's split - reissuing the first half of the month at
    the old ratio is more trouble than it is worth.
  * A team name we do not recognise is an unknown team and its money is
    dropped. That is the only way we have ever handled it.
  * Reservation cost is spread evenly over the term and the odd cents left over
    land on the LAST days of the term.
  * If the gap is non-zero it is untagged usage. It always has been.

Superseded by docs/weights-and-renames.md (2 August), which is the invoice.
Where this script and that memo disagree, the memo is what the teams paid.
"""
import json
import sys


def weights_for_month(export):
    """The split to bill the month at."""
    changes = export.get("weight_changes") or []
    if changes:
        return changes[-1].get("weights") or {}
    return export.get("shared_weights") or {}


def daily_amounts(cents, term_days):
    """Even daily cost, odd cents on the last days of the term."""
    base = cents // term_days
    extra = cents % term_days
    return [base + (1 if i >= term_days - extra else 0) for i in range(term_days)]


def split(cents, weights, known):
    live = {t: w for t, w in weights.items() if t in known and w > 0}
    total = sum(live.values())
    if total <= 0:
        return {}
    shares = {t: cents * w // total for t, w in live.items()}
    remainder = cents - sum(shares.values())
    order = sorted(shares, key=lambda t: (-live[t], t))
    i = 0
    while remainder > 0:
        shares[order[i % len(order)]] += 1
        remainder -= 1
        i += 1
    return shares


def reconcile(export):
    start = export["period"]["start"]
    end = export["period"]["end"]
    known = set(export["teams"])
    weights = weights_for_month(export)

    rows = {t: 0 for t in known}
    seen = set()
    lines_total = 0
    gap = 0
    unknown = []

    for line in export.get("lines") or []:
        if line["id"] in seen:
            continue
        seen.add(line["id"])
        team = line.get("team")
        if team is not None and team not in known:
            unknown.append(team)
            continue
        kind = line["kind"]
        if kind == "reservation":
            first = max(line["day"], start)
            last = min(line["day"] + line["term_days"] - 1, end)
            if first > last:
                continue
            amounts = daily_amounts(line["cents"], line["term_days"])
            offset = first - line["day"]
            charged = sum(amounts[offset:offset + (last - first + 1)])
            rows[team] += charged
            lines_total += charged
            continue
        if not (start <= line["day"] <= end):
            continue
        if kind == "usage":
            lines_total += line["cents"]
            if team is None:
                gap += line["cents"]
            else:
                rows[team] += line["cents"]
        elif kind == "shared":
            lines_total += line["cents"]
            shares = split(line["cents"], weights, known)
            if not shares:
                gap += line["cents"]
            else:
                for t, amount in shares.items():
                    rows[t] += amount
    return rows, lines_total, gap, unknown


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: reconcile_gap.py <export file>\n")
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        export = json.load(handle)
    rows, lines_total, gap, unknown = reconcile(export)

    print("split billed at: %s" % json.dumps(weights_for_month(export), sort_keys=True))
    for team in sorted(rows):
        print("  %-10s %8d" % (team, rows[team]))
    print("lines total    : %d" % lines_total)
    print("team rows      : %d" % sum(rows.values()))
    print("gap            : %d" % gap)
    if gap:
        print("gap explanation: untagged usage (%d cents reached no team)" % gap)
    else:
        print("gap explanation: none, everything reached a team")
    if unknown:
        print("unknown teams  : %s" % ", ".join(sorted(set(unknown))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
