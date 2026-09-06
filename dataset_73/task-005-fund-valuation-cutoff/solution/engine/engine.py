"""Fund NAV valuation engine.

Resolves a dealing instruction to a valuation date, selects the price record in
force at that dealing point, restates it onto the current unit basis and
publishes a NAV per unit before valuing the position.
"""
from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

_CENT = Decimal("0.01")
_UNIT = Decimal("0.0001")

_NORMAL_DEADLINE = (16, 0, 0)
_EARLY_DEADLINE = (13, 0, 0)
_DEFAULT_OFFSET = dt.timedelta(hours=-5)


class StaleAuthorityError(Exception):
    """Raised when no pricing authority is in force for the resolved dealing point."""


def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _as_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value).strip())


def _parse_offset(text) -> dt.timedelta:
    """A UTC offset such as -05:00 or +00:00, as a timedelta."""
    if isinstance(text, dt.timedelta):
        return text
    s = str(text).strip()
    if s in ("Z", "z", "UTC"):
        return dt.timedelta(0)
    sign = -1 if s[0] == "-" else 1
    s = s.lstrip("+-")
    hours, _, minutes = s.partition(":")
    return sign * dt.timedelta(hours=int(hours), minutes=int(minutes or 0))


def _parse_instant(text):
    """Parse an ISO-8601 timestamp (offset optional)."""
    s = str(text).strip().replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s)


def _rows(source, columns):
    """Normalise a config value into a list of dicts.

    Accepts a path to a CSV carrying those columns, a list of dicts, or a list
    of tuples positionally matching `columns`.
    """
    if source is None:
        return []
    if isinstance(source, str):
        with open(source, newline="", encoding="utf-8") as fh:
            return [dict(r) for r in csv.DictReader(fh)]
    out = []
    for row in source:
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            out.append({c: v for c, v in zip(columns, row)})
    return out


class FundNavEngine:
    """Compute the NAV contribution of a unit position at a dealing point."""

    def __init__(self, config=None):
        self._records = []
        self._holidays = set()
        self._early = set()
        self._offsets = []
        self._actions = []
        self._max_age_sessions = None
        if config:
            self.configure(config)

    # ------------------------------------------------------------------ config

    def reset(self):
        """Clear the price series. Calendar / offsets / actions / policy stay."""
        self._records = []

    def configure(self, options):
        options = options or {}
        if "prices" in options:
            self._records = []
            for row in _rows(options["prices"], ("price_date", "price", "published_at")):
                self._add_record(row)
        if "calendar" in options:
            self._holidays = set()
            self._early = set()
            for row in _rows(options["calendar"], ("date", "status")):
                day = _as_date(row["date"])
                status = str(row.get("status", "SESSION")).strip().upper()
                if status == "HOLIDAY":
                    self._holidays.add(day)
                elif status == "EARLY":
                    self._early.add(day)
        if "offsets" in options:
            self._offsets = []
            for row in _rows(options["offsets"], ("start_date", "end_date", "utc_offset")):
                self._offsets.append((
                    _as_date(row["start_date"]),
                    _as_date(row["end_date"]),
                    _parse_offset(row["utc_offset"]),
                ))
        if "actions" in options:
            self._actions = []
            for row in _rows(options["actions"], ("ex_date", "factor", "announced_on")):
                self._actions.append((_as_date(row["ex_date"]), _dec(row["factor"])))
        if "policy" in options:
            policy = options["policy"] or {}
            if "max_price_age_sessions" in policy:
                limit = policy["max_price_age_sessions"]
                self._max_age_sessions = None if limit is None else int(limit)

    def add_price(self, date_str, price, published_at=None):
        """Add one price record. `published_at` is optional (legacy 2-tuple form)."""
        self._add_record({"price_date": date_str, "price": price,
                          "published_at": published_at})

    def _add_record(self, row):
        published = row.get("published_at") or None
        instant = None
        if published:
            stamp = _parse_instant(published)
            if stamp.tzinfo is None:
                offset = self._offset_for(stamp.date())
                stamp = stamp.replace(tzinfo=dt.timezone(offset))
            instant = stamp.astimezone(dt.timezone.utc)
        self._records.append({
            "price_date": _as_date(row["price_date"]),
            "published_at": instant,
            "price": _dec(row["price"]),
            "seq": len(self._records),
        })

    # ---------------------------------------------------------------- calendar

    def _is_session(self, day):
        return day.weekday() < 5 and day not in self._holidays

    def _next_session(self, day):
        for _ in range(400):
            if self._is_session(day):
                return day
            day += dt.timedelta(days=1)
        raise StaleAuthorityError("no dealing session found near %s" % day)

    def _deadline(self, day):
        return _EARLY_DEADLINE if day in self._early else _NORMAL_DEADLINE

    def _offset_for(self, day):
        for start, end, offset in self._offsets:
            if start <= day <= end:
                return offset
        return _DEFAULT_OFFSET

    def _sessions_between(self, start_exclusive, end_inclusive):
        """Number of dealing sessions in (start_exclusive, end_inclusive]."""
        count = 0
        day = start_exclusive + dt.timedelta(days=1)
        while day <= end_inclusive:
            if self._is_session(day):
                count += 1
            day += dt.timedelta(days=1)
        return count

    # -------------------------------------------------------------- resolution

    def resolve_valuation_date(self, cutoff):
        """Resolve an instruction cutoff to the dealing session that prices it."""
        text = str(cutoff).strip()
        if "T" not in text and " " not in text:
            return self._next_session(_as_date(text))

        stamp = _parse_instant(text)
        if stamp.tzinfo is None:
            offset = self._offset_for(stamp.date())
            stamp = stamp.replace(tzinfo=dt.timezone(offset))
        utc = stamp.astimezone(dt.timezone.utc).replace(tzinfo=None)
        offset = self._offset_for(utc.date())
        local = utc + offset
        refined = self._offset_for(local.date())
        if refined != offset:
            local = utc + refined
        day = local.date()
        session = self._next_session(day)
        if session == day:
            hour, minute, second = self._deadline(day)
            limit = local.replace(hour=hour, minute=minute, second=second, microsecond=0)
            if local > limit:
                session = self._next_session(day + dt.timedelta(days=1))
        return session

    def _strike_instant(self, valuation_date):
        """The instant the books close for `valuation_date`, in UTC."""
        hour, minute, second = self._deadline(valuation_date)
        local = dt.datetime.combine(valuation_date, dt.time(hour, minute, second))
        return (local - self._offset_for(valuation_date)).replace(tzinfo=dt.timezone.utc)

    # --------------------------------------------------------------- valuation

    def _applicable_record(self, valuation_date):
        strike = self._strike_instant(valuation_date)
        visible = [r for r in self._records
                   if r["price_date"] <= valuation_date
                   and (r["published_at"] is None or r["published_at"] <= strike)]
        if not visible:
            return None
        best_date = max(r["price_date"] for r in visible)
        same_day = [r for r in visible if r["price_date"] == best_date]
        floor = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        return max(same_day, key=lambda r: (r["published_at"] or floor, r["seq"]))

    def _adjustment_divisor(self, price_date, valuation_date):
        divisor = Decimal(1)
        for ex_date, factor in self._actions:
            if price_date < ex_date <= valuation_date:
                divisor *= factor
        return divisor

    def _price_in_force(self, cutoff):
        valuation_date = self.resolve_valuation_date(cutoff)
        record = self._applicable_record(valuation_date)
        if record is None:
            raise StaleAuthorityError(
                "no price record in force at %s" % valuation_date.isoformat())
        if self._max_age_sessions is not None:
            age = self._sessions_between(record["price_date"], valuation_date)
            if age > self._max_age_sessions:
                raise StaleAuthorityError(
                    "price of %s is %d sessions old at %s"
                    % (record["price_date"].isoformat(), age,
                       valuation_date.isoformat()))
        divisor = self._adjustment_divisor(record["price_date"], valuation_date)
        return record["price"] / divisor

    def nav_per_unit(self, cutoff):
        """The published NAV per unit at the dealing point, to 4 decimal places."""
        return float(self._price_in_force(cutoff).quantize(_UNIT, rounding=ROUND_HALF_UP))

    def nav(self, cutoff, units):
        per_unit = self._price_in_force(cutoff).quantize(_UNIT, rounding=ROUND_HALF_UP)
        value = (per_unit * _dec(units)).quantize(_CENT, rounding=ROUND_HALF_UP)
        return float(value)

    def is_stale(self, cutoff):
        try:
            self._price_in_force(cutoff)
        except StaleAuthorityError:
            return True
        return False
