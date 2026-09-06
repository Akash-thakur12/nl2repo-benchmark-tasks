import datetime as dt
import json
from pathlib import Path

import pytest
from engine.engine import GpsRolloverEngine, ValidationError

DATA = Path(__file__).resolve().parent / "data"


def _rows(name):
    with open(DATA / name) as handle:
        return [json.loads(line) for line in handle if line.strip()]


SAMPLE_ROWS = _rows("sample_frames.jsonl")
HOLDOUT_ROWS = _rows("holdout_frames.jsonl")


# ---------------------------------------------------------------------------
# L0 -- week/date era resolution (unchanged behaviour)
# ---------------------------------------------------------------------------

def test_disambiguates_to_recent_era():
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_date(2330, 0) == dt.date(2024, 9, 1)


def test_epoch0_anchor():
    e = GpsRolloverEngine({"ref": "2019-04-07"})
    assert e.to_date(0, 0) == dt.date(1999, 8, 22)


def test_epoch1_anchor():
    e = GpsRolloverEngine({"ref": "2020-01-01"})
    assert e.to_date(0, 0) == dt.date(2019, 4, 7)


def test_epoch2_anchor():
    e = GpsRolloverEngine({"ref": "2039-01-01"})
    assert e.to_date(0, 0) == dt.date(2038, 11, 21)


def test_dow_offset():
    e = GpsRolloverEngine({"ref": "2019-04-13"})
    assert e.to_date(0, 6) == dt.date(1999, 8, 28)


@pytest.mark.parametrize("week,dow", [(70000, 0), (-1, 0), (65536, 0), (100, 7), (100, -1)])
def test_validation(week, dow):
    e = GpsRolloverEngine()
    with pytest.raises(ValidationError):
        e.to_date(week, dow)


@pytest.mark.parametrize("w,dow", [(0, 0), (1023, 6), (1024, 0), (2050, 3), (65535, 6)])
def test_to_date_returns_a_date(w, dow):
    e = GpsRolloverEngine()
    assert isinstance(e.to_date(w, dow), dt.date)


def test_from_date():
    e = GpsRolloverEngine()
    assert e.from_date(dt.date(1999, 8, 22)) == (0, 0)
    assert e.from_date(dt.date(1999, 8, 29)) == (1, 0)
    assert e.from_date(dt.date(2019, 4, 7)) == (1024, 0)
    weeks, dow = e.from_date(dt.date(2000, 1, 1))
    assert isinstance(weeks, int) and 0 <= dow <= 6


def test_reset_and_configure():
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    baseline = e.to_date(2330, 0)
    assert e.to_date(2330, 0) == baseline
    e.configure({"ref": "2019-04-07"})
    assert e.to_date(0, 0) == dt.date(1999, 8, 22)
    e.reset()
    assert e.to_date(2330, 0) == baseline


# ---------------------------------------------------------------------------
# L1 -- the era rule in detail (crux C)
# ---------------------------------------------------------------------------

def test_era_candidates_tested_in_ascending_order():
    """AN-0611 s3: the OLDEST qualifying era wins, not the most recent anchor.

    raw week 351 with ref 2026-01-01 qualifies under era 0 (2006-05-14). The
    AN-0417 'most recent anchor' reading answers 2025-12-28, twenty years out.
    """
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_date(351, 0) == dt.date(2006, 5, 14)
    assert e.resolve_week(351, "lnav") == 351


def test_era_grace_of_thirty_days_is_part_of_the_rule():
    """AN-0611 s3: the window is 1024 weeks PLUS 30 days.

    raw 0 with ref exactly on the era-1 anchor is 1024*7 days old, and raw 348
    with ref 2026-01-01 is 7193 days old -- 25 days inside the grace. Dropping
    the grace moves both by a full era.
    """
    assert GpsRolloverEngine({"ref": "2019-04-07"}).to_date(0, 0) == dt.date(1999, 8, 22)
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_date(348, 0) == dt.date(2006, 4, 23)
    assert (dt.date(2026, 1, 1) - dt.date(2006, 4, 23)).days == 1024 * 7 + 25


def test_era_boundary_is_sharp_at_the_grace_edge():
    """One raw week either side of the grace edge lands in a different era."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.resolve_week(348, "lnav") == 348
    assert e.resolve_week(347, "lnav") == 1371


def test_era_candidate_includes_the_requested_day_of_week():
    """AN-0611 s3: the candidate is the anchor advanced by weeks AND dow.

    The comparison against the reference date is made on that whole candidate,
    so the era can flip inside a single raw week. raw 347 with ref 2026-01-01:
    dow 1 is 7199 days before ref (one day outside the grace) and lands in era
    1; dow 5 is 7195 days and still qualifies for era 0. Choosing the era on
    dow 0 alone and adding the day afterwards answers era 1 for both.
    """
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_date(347, 5) == dt.date(2006, 4, 21)
    assert e.to_date(347, 1) == dt.date(2025, 12, 1)


def test_era_fallback_when_no_anchor_qualifies():
    """AN-0611 s3: if no candidate qualifies, era 0 is used unconditionally."""
    e = GpsRolloverEngine({"ref": "1999-01-01"})
    assert e.to_date(5, 0) == dt.date(1999, 8, 22) + dt.timedelta(weeks=5)


# ---------------------------------------------------------------------------
# L2 -- the leap-second history (crux I)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("iso,expected", [
    ("1999-06-01T00:00:00", 13),
    ("2003-06-15T00:00:00", 13),
    ("2009-03-22T00:00:00", 15),
    ("2013-01-01T00:00:00", 16),
    ("2026-01-01T00:00:00", 18),
])
def test_leap_offset_uses_the_value_in_force_at_the_instant(iso, expected):
    """AN-0611 s6.2: not the current offset, and not the offset at ref."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.leap_offset(dt.datetime.fromisoformat(iso)) == expected


def test_leap_offset_picks_the_right_effective_column():
    """AN-0611 s6.2: UTC arguments use utc_effective, GPS arguments gps_effective.

    The 2017 step is at 2017-01-01T00:00:00 UTC but 2017-01-01T00:00:17 GPS.
    """
    e = GpsRolloverEngine()
    probe = dt.datetime(2017, 1, 1, 0, 0, 0)
    assert e.leap_offset(probe, "utc") == 18
    assert e.leap_offset(probe, "gps") == 17
    assert e.leap_offset(dt.datetime(2017, 1, 1, 0, 0, 17), "gps") == 18


def test_leap_offset_before_the_first_tabulated_row_is_zero():
    """GPS-UTC was zero at the GPS epoch; the table starts from there."""
    e = GpsRolloverEngine()
    assert e.leap_offset(dt.datetime(1980, 1, 6)) == 0
    aware = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    assert e.leap_offset(aware) == 18


def test_leap_offset_rejects_an_unknown_scale():
    """scale must be 'utc' or 'gps'."""
    e = GpsRolloverEngine()
    with pytest.raises(ValidationError):
        e.leap_offset(dt.datetime(2020, 1, 1), "tai")


def test_decoded_instant_uses_the_historical_offset():
    """A 2003 and a 2009 frame must carry offsets 13 and 15, not 18.

    Reading 18 everywhere shifts these by five and three seconds; applying no
    leap correction at all moves the 2003 row onto the following date.
    """
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_utc(199, 1, "cnav") == dt.datetime(2003, 6, 14, 23, 59, 47)
    assert e.to_utc(500, 1, "cnav") == dt.datetime(2009, 3, 21, 23, 59, 45)


def test_decoded_instant_at_the_2017_leap_boundary():
    """The forward path compares the GPS instant against gps_effective."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_utc(906, 1, "cnav") == dt.datetime(2016, 12, 31, 23, 59, 43)


# ---------------------------------------------------------------------------
# L3 -- HOW TOW-count semantics (crux E)
# ---------------------------------------------------------------------------

def test_tow_count_names_the_next_subframe():
    """ICD 20.3.3.2: the count is the leading edge of the NEXT subframe.

    So tow_count=1 is the first subframe of the week, at second 0.
    """
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_utc(282, 1, "lnav") == dt.datetime(2024, 8, 31, 23, 59, 42)


def test_tow_count_zero_is_the_last_subframe_of_the_week():
    """AN-0611 s6.1: a zero count is the END of week WN, seven days later.

    The naive reading answers 2024-08-31 -- a different week and month.
    """
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_utc(282, 0, "lnav") == dt.datetime(2024, 9, 7, 23, 59, 36)


def test_adjacent_subframes_are_six_seconds_apart():
    """300 bits at 50 bit/s = 6 s; derived, never hard-coded from a note."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    first = e.to_utc(282, 50000, "lnav")
    second = e.to_utc(282, 50001, "lnav")
    assert (second - first).total_seconds() == 6
    assert first == dt.datetime(2024, 9, 4, 11, 19, 36)


def test_tow_count_range_is_narrower_than_the_field():
    """ICD 20.3.3.2: 0..100799, even though 17 bits allow 131071."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert isinstance(e.to_utc(282, 100799, "lnav"), dt.datetime)
    for bad in (100800, 131071, -1):
        with pytest.raises(ValidationError):
            e.to_utc(282, bad, "lnav")


def test_tow_day_boundary_lands_before_midnight():
    """A day-boundary count decodes to 23:59:36, not 23:59:42."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_utc(282, 14400, "lnav") == dt.datetime(2024, 9, 1, 23, 59, 36)


# ---------------------------------------------------------------------------
# L4 -- the four week fields and the WNa pivot (crux H)
# ---------------------------------------------------------------------------

def test_cnav_week_is_absolute():
    """13-bit CNAV carries the full week; no era rule is applied to it."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.resolve_week(199, "cnav") == 199
    assert e.resolve_week(8191, "cnav") == 8191


def test_almanac_pivots_forward_on_its_own_ephemeris_week():
    """WNa is modulo 256 and nearest to the CARRYING subframe's week.

    Ephemeris week 1306 with WNa 100 resolves forward to 1380. Treating WNa as
    10-bit gives 1124, and flooring to the most recent congruent week also
    gives 1124 -- five years out.
    """
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    eph = e.resolve_week(282, "lnav")
    assert eph == 1306
    assert e.resolve_week(100, "almanac", eph) == 1380


def test_almanac_pivots_backward_on_an_older_ephemeris_week():
    """The same WNa on ephemeris week 1140 resolves back to 1124.

    Pivoting on the reference date instead of the record's own week gives 1380.
    """
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    eph = e.resolve_week(116, "lnav")
    assert eph == 1140
    assert e.resolve_week(100, "almanac", eph) == 1124


def test_almanac_tie_resolves_to_the_earlier_week():
    """AN-0611 s5: a tie at exactly 128 weeks resolves to the earlier week."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.resolve_week(223, "almanac", 1375) == 1247


def test_almanac_requires_the_carrying_week():
    """WNa cannot be resolved without the subframe week that carried it."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    with pytest.raises(ValidationError):
        e.resolve_week(100, "almanac")


def test_bdt_uses_its_own_epoch_and_scale_offset():
    """BDT is 13-bit absolute against its own epoch and runs behind GPS."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.to_utc(500, 43200, "bdt") == dt.datetime(2015, 8, 4, 23, 59, 51)


@pytest.mark.parametrize("source,bad", [
    ("lnav", 1024), ("almanac", 256), ("cnav", 8192), ("bdt", 8192), ("lnav", -1),
])
def test_raw_week_must_fit_the_field_width(source, bad):
    """Each source has its own field width; out-of-range raw weeks are rejected."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    with pytest.raises(ValidationError):
        e.resolve_week(bad, source, 1306)


def test_unknown_source_is_rejected():
    """Only the sources listed in environment/data/ are decodable."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    with pytest.raises(ValidationError):
        e.resolve_week(1, "glonass")


def test_almanac_decode_chains_every_rule():
    """One almanac record: era rule -> eph week -> WNa pivot -> TOW -> leap."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    eph = e.resolve_week(282, "lnav")
    assert e.to_utc(100, 43200, "almanac", eph) == dt.datetime(2026, 2, 3, 23, 59, 36)


# ---------------------------------------------------------------------------
# L5 -- the inverse conversion
# ---------------------------------------------------------------------------

def test_from_utc_returns_the_next_subframe_count():
    """The inverse of the HOW semantics: second 0 of week 1306 is count 1."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.from_utc(dt.datetime(2024, 8, 31, 23, 59, 42)) == (1306, 1)


def test_from_utc_uses_the_utc_effective_column():
    """The inverse path has a UTC instant in hand (AN-0611 s6.2)."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.from_utc(dt.datetime(2016, 12, 31, 23, 59, 43)) == (906, 1)


@pytest.mark.parametrize("week,tow", [(1306, 0), (1306, 1), (906, 1), (500, 50000), (199, 14403)])
def test_to_utc_from_utc_round_trip(week, tow):
    """from_utc is the exact inverse of to_utc for the GPS week numbering."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.from_utc(e.to_utc(week, tow, "cnav")) == (week, tow)


def test_from_utc_validation():
    """The era-0 anchor itself is legal; earlier or off-boundary instants are not."""
    e = GpsRolloverEngine({"ref": "2026-01-01"})
    assert e.from_utc(dt.datetime(1999, 8, 21, 23, 59, 47)) == (0, 1)
    with pytest.raises(ValidationError):
        e.from_utc(dt.datetime(1990, 1, 1))
    with pytest.raises(ValidationError):
        e.from_utc(dt.datetime(2024, 8, 31, 23, 59, 43))


# ---------------------------------------------------------------------------
# L6 -- corpus replay
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("row", SAMPLE_ROWS, ids=[r["id"] for r in SAMPLE_ROWS])
def test_sample_corpus_replay(row):
    """Every frame shipped in environment/samples/ decodes to its recorded UTC."""
    e = GpsRolloverEngine({"ref": row["ref"]})
    got = e.to_utc(row["raw_week"], row["tow_count"], row["source"], row["current_week"])
    assert got == dt.datetime.fromisoformat(row["expected_utc"]), row["note"]


@pytest.mark.parametrize("row", HOLDOUT_ROWS, ids=[r["id"] for r in HOLDOUT_ROWS])
def test_holdout_corpus_replay(row):
    """Held-out frames, not shipped in environment/, decode correctly too."""
    e = GpsRolloverEngine({"ref": row["ref"]})
    assert e.resolve_week(row["raw_week"], row["source"], row["current_week"]) == row["expected_week"]
    got = e.to_utc(row["raw_week"], row["tow_count"], row["source"], row["current_week"])
    assert got == dt.datetime.fromisoformat(row["expected_utc"]), row["note"]
