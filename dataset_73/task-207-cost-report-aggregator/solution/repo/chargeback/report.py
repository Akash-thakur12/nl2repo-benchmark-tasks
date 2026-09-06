"""The aggregation itself (spec sections 1-7)."""
import json

from .money import (canonical_team, daily_split, fold_weights,
                    weighted_split, weights_in_force)


class Ledger:
    """One team's running charge, kept in the three buckets the report wants."""

    __slots__ = ("usage", "amortised", "shared", "credit")

    def __init__(self):
        self.usage = 0
        self.amortised = 0
        self.shared = 0
        self.credit = 0

    @property
    def charge(self):
        return self.usage + self.amortised + self.shared

    @property
    def outstanding(self):
        """6.2: what a credit can still be applied against."""
        return max(self.charge - self.credit, 0)

    def as_row(self):
        return {"usage": self.usage, "amortised": self.amortised,
                "shared": self.shared, "credit": self.credit,
                "total": self.charge - self.credit}          # 7.1


class Aggregator:
    def __init__(self, export):
        self.start = export["period"]["start"]
        self.end = export["period"]["end"]
        self.teams = list(export["teams"])
        self.known = set(self.teams)
        # A retired team name is the same team; the collector still emits some.
        self.renames = dict(export.get("renamed_from") or {})
        # shared_weights is the split in force at the start of the period; each
        # weight_changes entry replaces it from its own day onward.
        self.base_weights = export.get("shared_weights") or {}
        self.amendments = list(export.get("weight_changes") or [])
        self.ledgers = {team: Ledger() for team in self.teams}
        self.unallocated = 0
        self.unused_credit = 0
        self.errors = []
        self._seen = set()
        self._credits = []

    # ---------------------------------------------------------------- checks
    def _in_period(self, day):
        return self.start <= day <= self.end                 # 1.1, 1.2

    def _reject(self, code, detail):
        self.errors.append({"code": code, "detail": detail})

    # ----------------------------------------------------------------- lines
    def feed(self, line):
        line_id = line["id"]
        if line_id in self._seen:                            # 2.2 the first stands
            self._reject("DUPLICATE_LINE", line_id)
            return
        self._seen.add(line_id)

        written = line.get("team")
        team = None
        if written is not None:
            team = canonical_team(written, self.renames)     # rename memo
            if team not in self.known:                       # 2.3
                # Reported under the name the line carries, not the successor.
                self._reject("UNKNOWN_TEAM", written)
                return

        kind = line["kind"]
        if kind == "reservation":
            self._reservation(line, team)                    # 4.5 not day-gated
            return
        if not self._in_period(line["day"]):
            return
        if kind == "usage":
            self._usage(line, team)
        elif kind == "shared":
            self._shared(line)
        elif kind == "credit":
            self._credits.append((team, line["cents"]))      # 6.1 settled later
        else:
            raise ValueError("unrecognised line kind {0!r}".format(kind))

    def _usage(self, line, team):
        if team is None:
            self.unallocated += line["cents"]                # 3.2 never dropped
        else:
            self.ledgers[team].usage += line["cents"]        # 3.1

    def _shared(self, line):
        raw = weights_in_force(line["day"], self.base_weights, self.amendments)
        weights = fold_weights(raw, self.renames, self.known)  # 5.5 + renames
        shares = weighted_split(line["cents"], weights)
        if not shares:
            self.unallocated += line["cents"]                # 5.4
            return
        for team, amount in shares.items():
            self.ledgers[team].shared += amount              # 5.6

    def _reservation(self, line, team):
        term = line["term_days"]
        first = max(line["day"], self.start)
        last = min(line["day"] + term - 1, self.end)         # 4.1
        if first > last:
            return                                           # 4.3 wholly outside
        amounts = daily_split(line["cents"], term)           # 4.2
        offset = first - line["day"]
        span = last - first + 1
        self.ledgers[team].amortised += sum(amounts[offset:offset + span])  # 4.4

    # --------------------------------------------------------------- credits
    def settle(self):
        for team, cents in self._credits:                    # 6.1 in line order
            ledger = self.ledgers[team]
            usable = min(cents, ledger.outstanding)          # 6.2
            ledger.credit += usable                          # 6.4
            self.unused_credit += cents - usable             # 6.3

    def report(self):
        return {
            "teams": {team: self.ledgers[team].as_row() for team in self.teams},
            "unallocated": self.unallocated,
            "unused_credit": self.unused_credit,
            "errors": self.errors,
        }


def aggregate(export):
    aggregator = Aggregator(export)
    for line in export.get("lines", []) or []:               # 2.1 file order
        aggregator.feed(line)
    aggregator.settle()
    return aggregator.report()


def aggregate_text(text):
    return aggregate(json.loads(text))
