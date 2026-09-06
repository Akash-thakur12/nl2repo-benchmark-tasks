"""Reference model for the on-call rotation planner, following
docs/rotation-spec.md literally. Section numbers in comments refer to that
document. This is the authority for expected output; nothing is hardcoded.
"""
import datetime
import json

ROTATION = "ROTATION"
SUBSTITUTE = "SUBSTITUTE"
OVERRIDE = "OVERRIDE"
UNCOVERED = "UNCOVERED"


def parse_date(text):
    return datetime.date(*(int(part) for part in text.split("-")))


class Engineer:
    def __init__(self, spec):
        self.name = spec["name"]
        self.max_shifts = spec.get("max_shifts")
        self.ranges = [(parse_date(r["from"]), parse_date(r["to"]))
                       for r in spec.get("unavailable") or []]
        self.days = 0

    def blocked_by_range(self, day):
        # 1.3, 3.1 both ends inclusive
        return any(start <= day <= end for start, end in self.ranges)

    def at_cap(self):
        # 3.2 already assigned max_shifts days
        return self.max_shifts is not None and self.days >= self.max_shifts


class Planner:
    def __init__(self, config):
        self.start = parse_date(config["start"])
        self.length = config["days"]
        self.start_index = config.get("start_index", 0)
        self.max_consecutive = config.get("max_consecutive")

        self.engineers = [Engineer(spec) for spec in config["engineers"]]
        self.by_name = {e.name: e for e in self.engineers}

        self.overrides = {}          # date -> engineer name
        self.errors = []
        self.assignments = []        # (date, name or None, reason)

    # ------------------------------------------------------------ overrides
    def add_override(self, record):
        day = parse_date(record["date"])
        name = record["engineer"]
        if name not in self.by_name:                             # 5.2
            self.errors.append({"code": "UNKNOWN_ENGINEER", "detail": name})
            return
        if not (0 <= (day - self.start).days < self.length):     # 5.3
            self.errors.append({"code": "OVERRIDE_OUT_OF_WINDOW",
                                "detail": record["date"]})
            return
        if day in self.overrides:                                # 5.4
            self.errors.append({"code": "DUPLICATE_OVERRIDE",
                                "detail": record["date"]})
            return
        self.overrides[day] = name

    # -------------------------------------------------------------- helpers
    def _consecutive_run(self, name):
        """3.3 how many days in a row, counting back from the day before."""
        run = 0
        for _, assigned, _reason in reversed(self.assignments):
            if assigned != name:
                break
            run += 1
        return run

    def _available(self, engineer, day):
        if engineer.blocked_by_range(day):                       # 3.1
            return False
        if engineer.at_cap():                                    # 3.2
            return False
        if self.max_consecutive is not None and \
                self._consecutive_run(engineer.name) >= self.max_consecutive:
            return False                                         # 3.3
        return True

    def _substitute(self, candidate_index, day):
        """4.3 fewest days so far, ties by rotation order after the candidate."""
        count = len(self.engineers)
        best = None
        for step in range(1, count + 1):
            engineer = self.engineers[(candidate_index + step) % count]
            if not self._available(engineer, day):
                continue
            if best is None or engineer.days < best.days:
                best = engineer
        return best

    # ---------------------------------------------------------------- plan
    def plan(self):
        count = len(self.engineers)
        for offset in range(self.length):
            day = self.start + datetime.timedelta(days=offset)
            candidate_index = (self.start_index + offset) % count if count else 0

            override = self.overrides.get(day)
            if override is not None:                             # 4.1
                self._assign(day, self.by_name[override], OVERRIDE)
                continue

            if count == 0:
                self._uncovered(day)
                continue

            candidate = self.engineers[candidate_index]
            if self._available(candidate, day):                  # 4.2
                self._assign(day, candidate, ROTATION)
                continue

            substitute = self._substitute(candidate_index, day)  # 4.3
            if substitute is None:
                self._uncovered(day)                             # 4.4
                continue
            self._assign(day, substitute, SUBSTITUTE)

    def _assign(self, day, engineer, reason):
        engineer.days += 1                                       # 5.6, 4.5
        self.assignments.append((day, engineer.name, reason))

    def _uncovered(self, day):
        self.assignments.append((day, None, UNCOVERED))
        self.errors.append({"code": "NO_ONE_AVAILABLE",
                            "detail": day.isoformat()})          # 4.4

    # -------------------------------------------------------------- report
    def report(self):
        handoffs = []
        previous = None
        for index, (day, name, _reason) in enumerate(self.assignments):
            if index and name != previous:                       # 6.1, 6.2, 6.3
                handoffs.append({"date": day.isoformat(), "from": previous,
                                 "to": name})
            previous = name
        return {
            "assignments": [{"date": day.isoformat(), "engineer": name,
                             "reason": reason}
                            for day, name, reason in self.assignments],  # 7.1
            "shifts": [{"engineer": e.name, "days": e.days}
                       for e in self.engineers],                          # 7.2
            "handoffs": handoffs,                                         # 7.3
            "errors": self.errors,                                        # 7.4
        }


def replay(records):
    planner = Planner(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] != "override":
            raise ValueError("unknown op %r" % (record["op"],))
        planner.add_override(record)                             # 5.5
    planner.plan()
    return planner.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("roster must begin with a config record")
    return replay(records)
