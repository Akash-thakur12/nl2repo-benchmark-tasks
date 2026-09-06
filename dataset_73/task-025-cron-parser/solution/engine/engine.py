from __future__ import annotations

import datetime as dt


class CronParserEngine:
    FIELDS_5 = ["minute", "hour", "dom", "month", "dow"]
    FIELDS_6 = ["second"] + FIELDS_5
    FIELDS_7 = FIELDS_6 + ["year"]
    RANGES = {
        "second": (0, 59), "minute": (0, 59), "hour": (0, 23),
        "dom": (1, 31), "month": (1, 12), "dow": (0, 7), "year": (1970, 2099),
    }

    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    # -------------------------------------------------------------- parse
    def _fields_for(self, parts):
        if len(parts) == 5:
            return self.FIELDS_5
        if len(parts) == 6:
            return self.FIELDS_6
        if len(parts) == 7:
            return self.FIELDS_7
        raise ValueError(f"need 5, 6 or 7 fields, got {len(parts)}")

    def parse(self, expr):
        parts = expr.split()
        fields = self._fields_for(parts)
        out = {}
        for name, val in zip(fields, parts):
            lo, hi = self.RANGES[name]
            values = self._parse_field(val, lo, hi)
            if name == "dow":
                values = sorted({0 if v == 7 else v for v in values})
            out[name] = values
        return out

    def _parse_field(self, val, lo, hi):
        result = set()
        for piece in val.split(","):
            if piece == "":
                raise ValueError("empty list element")
            step = 1
            if "/" in piece:
                piece, step_s = piece.split("/", 1)
                step = int(step_s)
                if step <= 0:
                    raise ValueError(f"step must be positive: {step}")
            if piece == "*":
                start, end = lo, hi
            elif "-" in piece:
                a, b = piece.split("-", 1)
                start, end = int(a), int(b)
                if start > end:
                    raise ValueError(f"inverted range {start}-{end}")
            else:
                start = end = int(piece)
            if not (lo <= start <= hi) or not (lo <= end <= hi):
                raise ValueError(f"value out of range: {start}-{end} (allowed {lo}-{hi})")
            for v in range(start, end + 1, step):
                result.add(v)
        return sorted(result)

    # ----------------------------------------------------------- next_after
    def next_after(self, expr, after_iso, horizon_days=1830):
        parts = expr.split()
        fields = self._fields_for(parts)
        sets = self.parse(expr)
        stars = {name for name, val in zip(fields, parts) if val == "*"}
        has_seconds = "second" in fields
        has_year = "year" in fields

        after = dt.datetime.fromisoformat(after_iso)
        step = dt.timedelta(seconds=1) if has_seconds else dt.timedelta(minutes=1)
        t = after.replace(microsecond=0)
        if not has_seconds:
            t = t.replace(second=0)
        t += step
        limit = after + dt.timedelta(days=horizon_days)

        while t <= limit:
            if self._matches(t, sets, stars, has_seconds, has_year):
                return t.isoformat()
            t += step
        raise ValueError("no matching time within the search horizon")

    @staticmethod
    def _matches(t, sets, stars, has_seconds, has_year):
        if has_seconds and t.second not in sets["second"]:
            return False
        if t.minute not in sets["minute"]:
            return False
        if t.hour not in sets["hour"]:
            return False
        if t.month not in sets["month"]:
            return False
        if has_year and t.year not in sets["year"]:
            return False
        cron_dow = (t.weekday() + 1) % 7          # Mon=0..Sun=6  ->  Sun=0..Sat=6
        dom_ok = t.day in sets["dom"]
        dow_ok = cron_dow in sets["dow"]
        if "dom" in stars and "dow" in stars:
            return True
        if "dom" in stars:
            return dow_ok
        if "dow" in stars:
            return dom_ok
        return dom_ok or dow_ok                    # Vixie-cron OR semantics
