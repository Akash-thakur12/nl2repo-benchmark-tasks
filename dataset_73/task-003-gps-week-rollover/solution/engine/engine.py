"""GPS / BeiDou broadcast time-decoding engine.

Implements the rules of AN-0611 rev C:

  * era resolution of a truncated week counter against a reference date
    (ascending era order, 1024 weeks + 30 days of grace, era-0 fallback),
  * the ICD-GPS-200 HOW TOW-count semantics (the count names the leading edge
    of the *next* subframe, so the subframe itself starts six seconds earlier
    and a count of zero is the final subframe of the transmitted week),
  * the GPS-UTC offset in force at the instant being decoded, taken from the
    IERS TAI-UTC history,
  * the four broadcast week fields (LNAV 10-bit, CNAV 13-bit, almanac WNa
    8-bit pivoted on the record's own ephemeris week, BDT 13-bit).

Standard library only, and no runtime dependency on files outside the package:
the tables below are transcribed from environment/data/.
"""
from __future__ import annotations

import datetime as dt


class ValidationError(Exception):
    """Raised for a field value outside its specified range."""


# --- era anchors (environment/data/epoch_anchors.csv) ------------------------
EPOCHS = [
    (0, dt.date(1999, 8, 22)),
    (1024, dt.date(2019, 4, 7)),
    (2048, dt.date(2038, 11, 21)),
]

#: Start of receiver week 0, i.e. the era-0 anchor, in the GPS time scale.
WEEK_ORIGIN = dt.datetime(1999, 8, 22, 0, 0, 0)

SECONDS_PER_WEEK = 604800
#: 300 bits per subframe at 50 bits per second (ICD-GPS-200 20.3.2).
SUBFRAME_SECONDS = 6
#: 604800 / 6 -- the count runs 0 .. 100799 even though the field is 17 bits.
TOW_COUNT_MODULUS = SECONDS_PER_WEEK // SUBFRAME_SECONDS

#: Grace applied to the era window, in days (AN-0611 rev C s3).
ERA_GRACE_DAYS = 30

# --- broadcast week fields (environment/data/constellations.csv) -------------
#: name -> (week_bits, absolute, week_epoch, seconds_behind_gps)
SOURCES = {
    "lnav": (10, False, dt.date(1999, 8, 22), 0),
    "cnav": (13, True, dt.date(1999, 8, 22), 0),
    "almanac": (8, False, dt.date(1999, 8, 22), 0),
    "bdt": (13, True, dt.date(2006, 1, 1), 14),
}

# --- IERS TAI-UTC history (environment/data/leap_seconds.tab) ----------------
# (utc_effective, tai_utc). GPS-UTC = TAI-UTC - 19, because GPS time was
# coincident with UTC at the GPS epoch 1980-01-06, when TAI-UTC was 19 s.
_TAI_UTC = [
    ("1980-01-01", 19),
    ("1981-07-01", 20),
    ("1982-07-01", 21),
    ("1983-07-01", 22),
    ("1985-07-01", 23),
    ("1988-01-01", 24),
    ("1990-01-01", 25),
    ("1991-01-01", 26),
    ("1992-07-01", 27),
    ("1993-07-01", 28),
    ("1994-07-01", 29),
    ("1996-01-01", 30),
    ("1997-07-01", 31),
    ("1999-01-01", 32),
    ("2006-01-01", 33),
    ("2009-01-01", 34),
    ("2012-07-01", 35),
    ("2015-07-01", 36),
    ("2017-01-01", 37),
]


def _build_leap_table():
    """[(utc_effective, gps_effective, gps_utc_offset)] in ascending order.

    A leap second takes effect at a UTC instant; the same step happens in the
    GPS scale that many seconds later, because GPS time does not step. The two
    effective columns are therefore not the same instant, and which one a
    lookup compares against depends on the scale of the argument.
    """
    rows = []
    previous = 0
    for iso, tai_utc in _TAI_UTC:
        utc_effective = dt.datetime.fromisoformat(iso + "T00:00:00")
        offset = tai_utc - 19
        gps_effective = utc_effective + dt.timedelta(seconds=previous)
        rows.append((utc_effective, gps_effective, offset))
        previous = offset
    return rows


LEAP_TABLE = _build_leap_table()


class GpsRolloverEngine:
    """Decode truncated broadcast week/time fields to absolute civil time."""

    DEFAULT_REF = "2026-01-01"

    def __init__(self, config=None):
        self._ref = dt.date.fromisoformat((config or {}).get("ref", self.DEFAULT_REF))

    # ------------------------------------------------------------------ setup
    def reset(self):
        self._ref = dt.date.fromisoformat(self.DEFAULT_REF)

    def configure(self, options):
        self._ref = dt.date.fromisoformat(options.get("ref", self.DEFAULT_REF))

    # -------------------------------------------------------------- era rule
    def to_date(self, week, dow=0):
        if not isinstance(week, int) or isinstance(week, bool):
            raise ValidationError("week must be an int")
        if not 0 <= week <= 65535:
            raise ValidationError("week out of range")
        if not isinstance(dow, int) or isinstance(dow, bool):
            raise ValidationError("dow must be an int")
        if not 0 <= dow <= 6:
            raise ValidationError("dow out of range")
        window = 1024 * 7 + ERA_GRACE_DAYS
        for base_week, anchor in EPOCHS:
            offset = (week - base_week) % 1024
            target = anchor + dt.timedelta(weeks=offset, days=dow)
            if 0 <= (self._ref - target).days <= window:
                return target
        base_week, anchor = EPOCHS[0]
        offset = (week - base_week) % 1024
        return anchor + dt.timedelta(weeks=offset, days=dow)

    def from_date(self, d):
        diff = (d - EPOCHS[0][1]).days
        return diff // 7, diff % 7

    # ------------------------------------------------------------ week fields
    def resolve_week(self, raw, source="lnav", current_week=None):
        """Full (untruncated) week number for a raw broadcast week field."""
        bits, absolute, _epoch, _behind = self._source(source)
        if not isinstance(raw, int) or isinstance(raw, bool):
            raise ValidationError("raw week must be an int")
        if not 0 <= raw < (1 << bits):
            raise ValidationError(
                "raw week out of range for %s (%d bits)" % (source, bits))

        if absolute:
            return raw

        if source == "almanac":
            # WNa is modulo 256 of the GPS week, and resolves to the congruent
            # week nearest the week of the subframe that carried it. A tie at
            # exactly +/-128 weeks resolves to the earlier week.
            if current_week is None:
                raise ValidationError("almanac WNa requires current_week")
            if not isinstance(current_week, int) or isinstance(current_week, bool):
                raise ValidationError("current_week must be an int")
            modulus = 1 << bits
            half = modulus // 2
            delta = (raw - current_week + half) % modulus - half
            return current_week + delta

        # LNAV: the era rule, expressed in the week domain.
        return self.from_date(self.to_date(raw, 0))[0]

    # ----------------------------------------------------------- leap seconds
    def leap_offset(self, when, scale="utc"):
        """GPS-UTC offset, in whole seconds, in force at ``when``.

        ``scale`` says which time scale ``when`` is expressed in, and therefore
        which effective-date column the lookup compares against.
        """
        if scale not in ("utc", "gps"):
            raise ValidationError("scale must be 'utc' or 'gps'")
        probe = self._as_datetime(when)
        offset = 0
        for utc_effective, gps_effective, value in LEAP_TABLE:
            effective = utc_effective if scale == "utc" else gps_effective
            if effective <= probe:
                offset = value
            else:
                break
        return offset

    # ------------------------------------------------------------ time decode
    def to_utc(self, raw_week, tow_count, source="lnav", current_week=None):
        """Decode a broadcast (week, TOW count) pair to naive UTC."""
        _bits, _absolute, epoch, behind = self._source(source)
        if not isinstance(tow_count, int) or isinstance(tow_count, bool):
            raise ValidationError("tow_count must be an int")
        if not 0 <= tow_count < TOW_COUNT_MODULUS:
            raise ValidationError(
                "tow_count out of range 0..%d" % (TOW_COUNT_MODULUS - 1))

        week = self.resolve_week(raw_week, source, current_week)

        # The HOW TOW count names the leading edge of the NEXT subframe, so
        # this subframe begins six seconds earlier -- and a count of zero is
        # the last subframe of the transmitted week, not the first.
        sow = (tow_count * SUBFRAME_SECONDS - SUBFRAME_SECONDS) % SECONDS_PER_WEEK

        origin = dt.datetime(epoch.year, epoch.month, epoch.day)
        instant = origin + dt.timedelta(weeks=week, seconds=sow)
        # Bring a constellation running behind GPS onto the GPS scale.
        instant = instant + dt.timedelta(seconds=behind)
        return instant - dt.timedelta(seconds=self.leap_offset(instant, "gps"))

    def from_utc(self, when):
        """Inverse of :meth:`to_utc` for the GPS LNAV/CNAV week numbering."""
        probe = self._as_datetime(when)
        gps = probe + dt.timedelta(seconds=self.leap_offset(probe, "utc"))
        elapsed = int((gps - WEEK_ORIGIN).total_seconds())
        if elapsed < 0:
            raise ValidationError("instant precedes the era-0 anchor")
        week, sow = divmod(elapsed, SECONDS_PER_WEEK)
        if sow % SUBFRAME_SECONDS:
            raise ValidationError("instant is not on a subframe boundary")
        tow_count = (sow // SUBFRAME_SECONDS + 1) % TOW_COUNT_MODULUS
        return week, tow_count

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _as_datetime(when):
        if isinstance(when, dt.datetime):
            probe = when
        elif isinstance(when, dt.date):
            probe = dt.datetime(when.year, when.month, when.day)
        else:
            raise ValidationError("expected a date or datetime")
        if probe.tzinfo is not None:
            probe = probe.replace(tzinfo=None)
        return probe

    def _source(self, source):
        try:
            return SOURCES[source]
        except (KeyError, TypeError):
            raise ValidationError("unknown source: %r" % (source,))
