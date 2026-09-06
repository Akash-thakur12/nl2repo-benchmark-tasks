"""Whole-cent arithmetic and the two pieces of team/weight bookkeeping that sit
in front of it (spec sections 4.2, 5.2, 5.5, and docs/weights-and-renames.md).

Every split here conserves the total exactly: the sum of what comes out always
equals what went in, which is the property the report is checked against.
"""


def daily_split(cents, term_days):
    """4.2: an even daily amount, with the remainder one extra cent on each of
    the earliest days of the term."""
    base = cents // term_days
    extra = cents % term_days
    return [base + (1 if day < extra else 0) for day in range(term_days)]


def canonical_team(name, renames):
    """A retired team name means the team it became.

    The collector was never updated after the July renames, so exports still
    carry retired names on lines and as weight keys. Resolving one is not an
    error and does not lose the money: it charges the successor.
    """
    seen = set()
    current = name
    while current in renames and current not in seen:
        seen.add(current)
        current = renames[current]
    return current


def weights_in_force(day, base_weights, amendments):
    """The split in force on a given day.

    `shared_weights` is the configuration at the start of the period; each entry
    of `weight_changes` replaces it from its own `day` onward. Finance lists the
    amendments in the order it applied them, which is not day order, so the one
    in force is the latest-dated entry on or before `day`, and a later position
    in the file wins a shared day. Applying the last-listed (or the last-dated)
    amendment to the whole period is the pre-fix behaviour that caused the July
    dispute; see docs/weights-and-renames.md.
    """
    chosen, key = None, None
    for index, amendment in enumerate(amendments):
        amendment_day = amendment["day"]
        if amendment_day > day:
            continue
        candidate = (amendment_day, index)
        if key is None or candidate > key:
            key, chosen = candidate, amendment
    if chosen is None:
        return base_weights
    return chosen.get("weights") or {}


def fold_weights(raw_weights, renames, known):
    """5.5 and the rename memo, in that order of subtlety.

    A weight filed under a retired name belongs to the successor and is added to
    whatever the successor was already given, so it *does* raise the total
    weight. A weight naming a team the report does not cover is dropped and does
    not. The folded keys are canonical, which is also what the 5.2 tie-break
    then sorts on.
    """
    folded = {}
    for name, weight in (raw_weights or {}).items():
        team = canonical_team(name, renames)
        if team not in known:
            continue
        folded[team] = folded.get(team, 0) + weight
    return folded


def weighted_split(cents, weights):
    """5.2, 5.3: floor by weight, then hand the remainder out one cent at a time
    in descending weight, ties broken by name ascending, wrapping if needed.

    Returns an empty mapping when there is nothing to split across, which the
    caller treats as unallocated (5.4).
    """
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

    queue = sorted(shares, key=lambda team: (-weights[team], team))
    position = 0
    while remainder > 0:
        shares[queue[position % len(queue)]] += 1
        remainder -= 1
        position += 1
    return shares
