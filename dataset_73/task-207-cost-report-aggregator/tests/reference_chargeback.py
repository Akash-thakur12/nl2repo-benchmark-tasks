"""Reference model for chargeback, following docs/chargeback-spec.md literally.

Section numbers in comments refer to that document; the two rules that document
delegates to docs/weights-and-renames.md (the as-of-day weight amendments of
section 5, and the retired team names of section 2) are marked with the memo
heading they come from. This is the authority for expected output; nothing is
hardcoded. Every amount is whole cents.
"""
import json


def resolve_team(name, renames):
    """Memo "A retired name is the same team": a name the collector still emits
    under its retired spelling means the team it became."""
    seen = set()
    current = name
    while current in renames and current not in seen:
        seen.add(current)
        current = renames[current]
    return current


def weights_as_of(day, base_weights, amendments):
    """Memo "Amendments take effect on their own day": the split in force for a
    line is the one from the latest amendment dated on or before the line's day,
    with a later entry in file order winning a shared day. `shared_weights` is
    the configuration in force at the start of the period."""
    chosen = None
    key = None
    for index, amendment in enumerate(amendments):
        amendment_day = amendment["day"]
        if amendment_day > day:
            continue
        candidate = (amendment_day, index)
        if key is None or candidate > key:
            key = candidate
            chosen = amendment
    if chosen is None:
        return base_weights
    return chosen.get("weights") or {}


def canonical_weights(raw_weights, renames, known):
    """5.5 plus the memo: a weight filed under a retired name folds into the
    successor's weight and so does count toward the total; a weight naming a
    team the report does not cover is dropped and does not."""
    folded = {}
    for name, weight in (raw_weights or {}).items():
        team = resolve_team(name, renames)
        if team not in known:                                 # 5.5
            continue
        folded[team] = folded.get(team, 0) + weight
    return folded


def amortised_days(day, term_days, start, end):
    """4.1-4.3: the days of the term that fall inside the period."""
    first = max(day, start)
    last = min(day + term_days - 1, end)
    return first, last


def daily_amounts(cents, term_days):
    """4.2: an even split, with the remainder one extra cent on the earliest days."""
    base = cents // term_days
    extra = cents % term_days
    return [base + (1 if index < extra else 0) for index in range(term_days)]


def split_shared(cents, weights, team_order=None):
    """5.2, 5.3: floor by weight, then the remainder by descending weight and
    ascending name.  The names here are already canonical, so the tie-break
    sorts on the name the report uses, not on the key as written."""
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return {}
    shares = {team: cents * weight // total_weight
              for team, weight in weights.items() if weight > 0}
    if not shares:
        return {}
    remainder = cents - sum(shares.values())
    if remainder <= 0:
        return shares
    eligible = sorted(shares, key=lambda team: (-weights[team], team))
    index = 0
    while remainder > 0:
        team = eligible[index % len(eligible)]
        shares[team] += 1
        remainder -= 1
        index += 1
    return shares


def aggregate(export):
    start = export["period"]["start"]
    end = export["period"]["end"]
    teams = list(export["teams"])
    known = set(teams)
    renames = dict(export.get("renamed_from") or {})
    base_weights = export.get("shared_weights") or {}
    amendments = list(export.get("weight_changes") or [])

    totals = {team: {"usage": 0, "amortised": 0, "shared": 0} for team in teams}
    unallocated = 0
    errors = []
    seen = set()
    pending_credits = []

    for line in export.get("lines", []) or []:
        line_id = line["id"]
        if line_id in seen:                                   # 2.2
            errors.append({"code": "DUPLICATE_LINE", "detail": line_id})
            continue
        seen.add(line_id)

        kind = line["kind"]
        written = line.get("team")
        team = None
        if written is not None:
            team = resolve_team(written, renames)             # memo, then 2.3
            if team not in known:
                errors.append({"code": "UNKNOWN_TEAM", "detail": written})
                continue

        if kind == "reservation":                             # 4.5 not day-gated
            first, last = amortised_days(line["day"], line["term_days"], start, end)
            if first > last:
                continue                                      # 4.3 entirely outside
            amounts = daily_amounts(line["cents"], line["term_days"])
            offset = first - line["day"]
            span = last - first + 1
            totals[team]["amortised"] += sum(amounts[offset:offset + span])
            continue

        if not (start <= line["day"] <= end):                 # 1.2
            continue

        if kind == "usage":
            if team is None:
                unallocated += line["cents"]                  # 3.2
            else:
                totals[team]["usage"] += line["cents"]        # 3.1
        elif kind == "shared":
            raw = weights_as_of(line["day"], base_weights, amendments)
            weights = canonical_weights(raw, renames, known)
            shares = split_shared(line["cents"], weights)
            if not shares:                                    # 5.4
                unallocated += line["cents"]
            else:
                for name, amount in shares.items():
                    totals[name]["shared"] += amount          # 5.6
        elif kind == "credit":
            pending_credits.append((team, line["cents"]))     # 6.1 applied later
        else:
            raise ValueError("unknown line kind %r" % (kind,))

    applied = {team: 0 for team in teams}
    unused_credit = 0
    for team, cents in pending_credits:                       # 6.1 in line order
        entry = totals[team]
        owed = entry["usage"] + entry["amortised"] + entry["shared"] - applied[team]
        usable = min(cents, max(owed, 0))                     # 6.2 never below zero
        applied[team] += usable
        unused_credit += cents - usable                       # 6.3

    report_teams = {}
    for team in teams:                                        # 7.1 every team
        entry = totals[team]
        report_teams[team] = {
            "usage": entry["usage"],
            "amortised": entry["amortised"],
            "shared": entry["shared"],
            "credit": applied[team],                          # 6.4
            "total": entry["usage"] + entry["amortised"] + entry["shared"]
            - applied[team],
        }

    return {"teams": report_teams, "unallocated": unallocated,
            "unused_credit": unused_credit, "errors": errors}


def aggregate_text(text):
    return aggregate(json.loads(text))
