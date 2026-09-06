"""The roster as configured: engineers, when they are away, what limits them
(spec sections 1 and 3)."""
import datetime


def iso(text):
    year, month, day = (int(part) for part in text.split("-"))
    return datetime.date(year, month, day)


class Away:
    """One unavailable range. Both ends belong to it (1.3)."""

    def __init__(self, span):
        self.first = iso(span["from"])
        self.last = iso(span["to"])

    def covers(self, day):
        return self.first <= day <= self.last


class Engineer:
    def __init__(self, spec):
        self.name = spec["name"]
        self.limit = spec.get("max_shifts")
        self.away = [Away(span) for span in spec.get("unavailable") or []]
        self.worked = 0

    def is_away(self, day):
        return any(span.covers(day) for span in self.away)         # 3.1

    def out_of_shifts(self):
        # 3.2 the cap is a number of days, so reaching it is enough
        return self.limit is not None and self.worked >= self.limit


class Roster:
    def __init__(self, config):
        self.first_day = iso(config["start"])
        self.length = config["days"]
        self.first_index = config.get("start_index", 0)
        self.run_limit = config.get("max_consecutive")
        self.engineers = [Engineer(spec) for spec in config["engineers"]]
        self.by_name = {engineer.name: engineer for engineer in self.engineers}

    def days(self):
        for offset in range(self.length):                          # 1.1
            yield offset, self.first_day + datetime.timedelta(days=offset)

    def in_window(self, day):
        return 0 <= (day - self.first_day).days < self.length

    def candidate_index(self, offset):
        # 2.1, 2.2 one step per day, whatever happened yesterday
        if not self.engineers:
            return 0
        return (self.first_index + offset) % len(self.engineers)
