#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out export catches it.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_chargeback as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "exports"


# ----------------------------------------------------------- shared variants
def split_lightest_first(cents, weights, _order):
    total = sum(weights.values())
    if total <= 0:
        return {}
    shares = {t: cents * w // total for t, w in weights.items() if w > 0}
    remainder = cents - sum(shares.values())
    eligible = sorted(shares, key=lambda t: (weights[t], t))
    index = 0
    while remainder > 0:
        shares[eligible[index % len(eligible)]] += 1
        remainder -= 1
        index += 1
    return shares


def split_by_name(cents, weights, _order):
    total = sum(weights.values())
    if total <= 0:
        return {}
    shares = {t: cents * w // total for t, w in weights.items() if w > 0}
    remainder = cents - sum(shares.values())
    eligible = sorted(shares)
    index = 0
    while remainder > 0:
        shares[eligible[index % len(eligible)]] += 1
        remainder -= 1
        index += 1
    return shares


def split_remainder_to_one(cents, weights, _order):
    total = sum(weights.values())
    if total <= 0:
        return {}
    shares = {t: cents * w // total for t, w in weights.items() if w > 0}
    remainder = cents - sum(shares.values())
    if remainder:
        first = sorted(shares, key=lambda t: (-weights[t], t))[0]
        shares[first] += remainder
    return shares


def split_drop_remainder(cents, weights, _order):
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {t: cents * w // total for t, w in weights.items() if w > 0}


# Deliberately not listed as a shortcut. A zero-weight team takes a share of
# zero and sorts last in the remainder order, and the remainder is always
# strictly smaller than the number of positive-weight teams, so it can never
# reach a zero-weight team. Including one changes nothing observable.
def split_zero_weight_shares_remainder(cents, weights, _order):
    total = sum(weights.values())
    if total <= 0:
        return {}
    shares = {t: cents * w // total for t, w in weights.items()}
    remainder = cents - sum(shares.values())
    eligible = sorted(shares, key=lambda t: (-weights[t], t))
    index = 0
    while remainder > 0:
        shares[eligible[index % len(eligible)]] += 1
        remainder -= 1
        index += 1
    return shares


# ------------------------------------------------------ reservation variants
def daily_latest_first(cents, term_days):
    base = cents // term_days
    extra = cents % term_days
    return [base + (1 if index >= term_days - extra else 0)
            for index in range(term_days)]


def split_raw_key_tie(cents, weights, raw_weights, renames):
    """5.2, but the remainder queue is ordered by the key as written in the
    weight table rather than by the name the report bills under. Only visible
    when a retired key ties with a canonical one."""
    total = sum(weights.values())
    if total <= 0:
        return {}
    shares = {t: cents * w // total for t, w in weights.items() if w > 0}
    if not shares:
        return {}
    written = {}
    for name in (raw_weights or {}):
        seen = set()
        cur = name
        while cur in renames and cur not in seen:
            seen.add(cur)
            cur = renames[cur]
        written.setdefault(cur, name)
    remainder = cents - sum(shares.values())
    order = sorted(shares, key=lambda t: (-weights[t], written.get(t, t)))
    index = 0
    while remainder > 0:
        shares[order[index % len(order)]] += 1
        remainder -= 1
        index += 1
    return shares


# -------------------------------------------------------------- the roll-up
def make_aggregate(split=None, daily=None, clip_before_split=False,
                   # term_end_exclusive is kept as an option but is not listed as
                   # a shortcut: an over-long term is either clipped back to the
                   # period end, or indexes past the end of the daily amounts,
                   # which slices to the same list. Neither is observable.
                   reservation_day_gated=False, term_end_exclusive=False,
                   drop_untagged=False, duplicate_last_wins=False,
                   duplicate_silent=False, unknown_team_silent=False,
                   credits_immediate=False, credits_go_negative=False,
                   ignore_unused_credit=False, omit_empty_teams=False,
                   total_ignores_credit=False, weights_count_unlisted=False,
                   zero_weight_total_is_error=False,
                   # the amendment and rename near-misses
                   ignore_amendments=False, amendment_last_listed=False,
                   amendment_latest_day_retroactive=False,
                   amendment_first_wins_a_shared_day=False,
                   ignore_renames=False, drop_retired_weight=False,
                   tie_break_on_raw_key=False):
    split = split or ref.split_shared
    daily = daily or ref.daily_amounts

    def do(export):
        start = export["period"]["start"]
        end = export["period"]["end"]
        teams = list(export["teams"])
        known = set(teams)
        base_weights = export.get("shared_weights") or {}
        amendments = list(export.get("weight_changes") or [])
        renames = {} if ignore_renames else dict(export.get("renamed_from") or {})

        def canonical(name):
            seen = set()
            cur = name
            while cur in renames and cur not in seen:
                seen.add(cur)
                cur = renames[cur]
            return cur

        def raw_for(day):
            """Which entry of weight_changes is in force for a line on `day`."""
            if ignore_amendments or not amendments:
                return base_weights
            if amendment_last_listed:
                return amendments[-1].get("weights") or {}
            if amendment_latest_day_retroactive:
                best = max(range(len(amendments)),
                           key=lambda i: (amendments[i]["day"], i))
                return amendments[best].get("weights") or {}
            live = [(a["day"], i, a) for i, a in enumerate(amendments)
                    if a["day"] <= day]
            if not live:
                return base_weights
            if amendment_first_wins_a_shared_day:
                top = max(d for d, _, _ in live)
                return min((e for e in live if e[0] == top))[2].get("weights") or {}
            return max(live)[2].get("weights") or {}

        def weights_for(day):
            folded = {}
            for name, weight in (raw_for(day) or {}).items():
                team = name if drop_retired_weight else canonical(name)
                if team not in known and not weights_count_unlisted:
                    continue
                folded[team] = folded.get(team, 0) + weight
            return folded

        totals = {t: {"usage": 0, "amortised": 0, "shared": 0} for t in teams}
        unallocated = 0
        errors = []
        seen = {}
        applied = {t: 0 for t in teams}
        unused = 0
        pending = []

        def charge_of(team):
            entry = totals[team]
            return entry["usage"] + entry["amortised"] + entry["shared"]

        def apply_credit(team, cents):
            nonlocal unused
            owed = charge_of(team) - applied[team]
            usable = cents if credits_go_negative else min(cents, max(owed, 0))
            applied[team] += usable
            if not ignore_unused_credit:
                unused += cents - usable

        for line in export.get("lines", []) or []:
            line_id = line["id"]
            if line_id in seen:
                if not duplicate_silent:
                    errors.append({"code": "DUPLICATE_LINE", "detail": line_id})
                if not duplicate_last_wins:
                    continue
            seen[line_id] = True

            kind = line["kind"]
            written = line.get("team")
            team = None
            if written is not None:
                team = canonical(written)
                if team not in known:
                    if not unknown_team_silent:
                        errors.append({"code": "UNKNOWN_TEAM", "detail": written})
                    continue

            if kind == "reservation":
                if reservation_day_gated and not (start <= line["day"] <= end):
                    continue
                term = line["term_days"]
                last_day = line["day"] + term - (0 if term_end_exclusive else 1)
                first = max(line["day"], start)
                last = min(last_day, end)
                if first > last:
                    continue
                span = last - first + 1
                if clip_before_split:
                    amounts = daily(line["cents"], span)
                    totals[team]["amortised"] += sum(amounts)
                else:
                    amounts = daily(line["cents"], term)
                    offset = first - line["day"]
                    totals[team]["amortised"] += sum(amounts[offset:offset + span])
                continue

            if not (start <= line["day"] <= end):
                continue

            if kind == "usage":
                if team is None:
                    if not drop_untagged:
                        unallocated += line["cents"]
                else:
                    totals[team]["usage"] += line["cents"]
            elif kind == "shared":
                weights = weights_for(line["day"])
                if zero_weight_total_is_error and sum(weights.values()) <= 0:
                    errors.append({"code": "NO_WEIGHTS", "detail": line_id})
                    continue
                if tie_break_on_raw_key:
                    shares = split_raw_key_tie(line["cents"], weights,
                                               raw_for(line["day"]), renames)
                else:
                    shares = split(line["cents"], weights, teams)
                if not shares:
                    unallocated += line["cents"]
                else:
                    for name, amount in shares.items():
                        if name in totals:
                            totals[name]["shared"] += amount
            elif kind == "credit":
                if credits_immediate:
                    apply_credit(team, line["cents"])
                else:
                    pending.append((team, line["cents"]))

        for team, cents in pending:
            apply_credit(team, cents)

        report = {}
        for team in teams:
            entry = totals[team]
            charge = entry["usage"] + entry["amortised"] + entry["shared"]
            if omit_empty_teams and charge == 0 and applied[team] == 0:
                continue
            report[team] = {
                "usage": entry["usage"], "amortised": entry["amortised"],
                "shared": entry["shared"], "credit": applied[team],
                "total": charge if total_ignores_credit else charge - applied[team],
            }
        return {"teams": report, "unallocated": unallocated,
                "unused_credit": unused, "errors": errors}
    return do


SHORTCUTS = [
    ("the shared remainder goes to the lightest weight first", make_aggregate(split=split_lightest_first)),
    ("the shared remainder is handed out by name alone", make_aggregate(split=split_by_name)),
    ("the whole shared remainder goes to one team", make_aggregate(split=split_remainder_to_one)),
    ("the shared remainder is dropped", make_aggregate(split=split_drop_remainder)),
    ("weights totalling zero is an error rather than unallocated", make_aggregate(zero_weight_total_is_error=True)),
    ("a weight for an unlisted team counts toward the total", make_aggregate(weights_count_unlisted=True)),
    ("a reservation remainder lands on the latest days", make_aggregate(daily=daily_latest_first)),
    ("a reservation is split across only the days inside the period", make_aggregate(clip_before_split=True)),
    ("a reservation dated outside the period is skipped", make_aggregate(reservation_day_gated=True)),
    ("untagged usage is dropped rather than left unallocated", make_aggregate(drop_untagged=True)),
    ("a duplicate id lets the later line win", make_aggregate(duplicate_last_wins=True)),
    ("a duplicate id is skipped without an error", make_aggregate(duplicate_silent=True)),
    ("an unknown team is skipped without an error", make_aggregate(unknown_team_silent=True)),
    ("credits are applied as they are read", make_aggregate(credits_immediate=True)),
    ("a credit may push a team below zero", make_aggregate(credits_go_negative=True)),
    ("credit that could not be applied is forgotten", make_aggregate(ignore_unused_credit=True)),
    ("a team with nothing charged is left out of the report", make_aggregate(omit_empty_teams=True)),
    ("the total does not subtract the credit", make_aggregate(total_ignores_credit=True)),
    ("weight_changes is ignored and shared_weights bills the whole period", make_aggregate(ignore_amendments=True)),
    ("the last-listed amendment bills the whole period", make_aggregate(amendment_last_listed=True)),
    ("the latest-dated amendment bills the whole period", make_aggregate(amendment_latest_day_retroactive=True)),
    ("the earlier entry wins when two amendments share a day", make_aggregate(amendment_first_wins_a_shared_day=True)),
    ("a retired team name is an unknown team", make_aggregate(ignore_renames=True)),
    ("a weight filed under a retired name is struck out", make_aggregate(drop_retired_weight=True)),
    ("the remainder tie-break sorts on the weight key as written", make_aggregate(tie_break_on_raw_key=True)),
]


def main():
    sample_files = sorted(SAMPLES.glob("*.export"))
    held_files = sorted(HELD_OUT.glob("*.export"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.aggregate_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.aggregate_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, fn in SHORTCUTS:
        ok = True
        for f in sample_files:
            try:
                if fn(json.loads(f.read_text(encoding="utf-8"))) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if fn(json.loads(f.read_text(encoding="utf-8"))) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out export:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
