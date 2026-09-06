"""Planning the window (spec sections 2, 4, 5, 6, 7)."""
import json

from .roster import Roster, iso

ROTATION = "ROTATION"
SUBSTITUTE = "SUBSTITUTE"
OVERRIDE = "OVERRIDE"
UNCOVERED = "UNCOVERED"


class Day:
    def __init__(self, date, engineer, reason):
        self.date = date
        self.engineer = engineer          # a name, or None
        self.reason = reason

    def rendered(self):
        return {"date": self.date.isoformat(), "engineer": self.engineer,
                "reason": self.reason}                             # 7.1


class Plan:
    def __init__(self, roster):
        self.roster = roster
        self.pinned = {}                  # date -> name
        self.errors = []
        self.days = []

    # ------------------------------------------------------------ overrides
    def pin(self, record):
        """Section 5, read before anything is planned."""
        name = record["engineer"]
        if name not in self.roster.by_name:                        # 5.2
            self._error("UNKNOWN_ENGINEER", name)
            return
        day = iso(record["date"])
        if not self.roster.in_window(day):                         # 5.3
            self._error("OVERRIDE_OUT_OF_WINDOW", record["date"])
            return
        if day in self.pinned:                                     # 5.4
            self._error("DUPLICATE_OVERRIDE", record["date"])
            return
        self.pinned[day] = name

    def _error(self, code, detail):
        self.errors.append({"code": code, "detail": detail})       # 7.4

    # -------------------------------------------------------------- helpers
    def _run_length(self, name):
        """3.3 how many days in a row up to yesterday, broken by anyone else
        and by a day nobody covered."""
        run = 0
        for day in reversed(self.days):
            if day.engineer != name:
                break
            run += 1
        return run

    def _free(self, engineer, date):
        if engineer.is_away(date):                                 # 3.1
            return False
        if engineer.out_of_shifts():                               # 3.2
            return False
        limit = self.roster.run_limit
        return limit is None or self._run_length(engineer.name) < limit   # 3.3

    def _stand_in(self, candidate_index, date):
        """4.3 fewest days so far; ties go to whoever comes first after the
        candidate."""
        engineers = self.roster.engineers
        chosen = None
        for step in range(1, len(engineers) + 1):
            engineer = engineers[(candidate_index + step) % len(engineers)]
            if self._free(engineer, date) and (chosen is None
                                               or engineer.worked < chosen.worked):
                chosen = engineer
        return chosen

    # ----------------------------------------------------------------- plan
    def fill(self):
        for offset, date in self.roster.days():
            pinned = self.pinned.get(date)
            if pinned is not None:                                 # 4.1
                self._take(date, self.roster.by_name[pinned], OVERRIDE)
                continue

            engineers = self.roster.engineers
            if not engineers:
                self._nobody(date)
                continue

            index = self.roster.candidate_index(offset)
            candidate = engineers[index]
            if self._free(candidate, date):                        # 4.2
                self._take(date, candidate, ROTATION)
                continue

            stand_in = self._stand_in(index, date)                 # 4.3
            if stand_in is None:
                self._nobody(date)                                 # 4.4
                continue
            self._take(date, stand_in, SUBSTITUTE)

    def _take(self, date, engineer, reason):
        engineer.worked += 1                                       # 4.5, 5.6
        self.days.append(Day(date, engineer.name, reason))

    def _nobody(self, date):
        self.days.append(Day(date, None, UNCOVERED))
        self._error("NO_ONE_AVAILABLE", date.isoformat())          # 4.4

    # --------------------------------------------------------------- report
    def _handoffs(self):
        out = []
        previous = None
        for index, day in enumerate(self.days):
            if index and day.engineer != previous:                 # 6.1-6.3
                out.append({"date": day.date.isoformat(), "from": previous,
                            "to": day.engineer})
            previous = day.engineer
        return out

    def report(self):
        return {
            "assignments": [day.rendered() for day in self.days],  # 7.1
            "shifts": [{"engineer": engineer.name, "days": engineer.worked}
                       for engineer in self.roster.engineers],     # 7.2
            "handoffs": self._handoffs(),                          # 7.3
            "errors": self.errors,                                 # 7.4
        }


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("roster must begin with a config record")
    plan = Plan(Roster(records[0]))
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] != "override":
            raise ValueError("unknown op %r" % (record["op"],))
        plan.pin(record)                                           # 5.5
    plan.fill()
    return plan.report()
