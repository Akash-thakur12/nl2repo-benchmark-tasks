import datetime as dt

import pytest
from engine.engine import FundNavEngine, StaleAuthorityError

SERIES = [("2024-12-30", 100.0), ("2025-01-02", 101.5), ("2025-01-03", 102.0)]


def test_nav_uses_latest_price_on_or_before_cutoff():
    e = FundNavEngine({"prices": SERIES})
    assert e.nav("2025-01-02", 10) == round(101.5 * 10, 4)
    assert e.nav("2025-01-03", 10) == round(102.0 * 10, 4)
    assert e.nav("2025-01-04", 10) == round(102.0 * 10, 4)   # no newer price exists


def test_not_latest_when_cutoff_is_early():
    e = FundNavEngine({"prices": SERIES})
    assert e.nav("2024-12-31", 1) == 100.0


def test_stale_before_first_price():
    e = FundNavEngine({"prices": SERIES})
    assert e.is_stale("2024-01-01") is True
    with pytest.raises(StaleAuthorityError):
        e.nav("2024-01-01", 1)


def test_empty_series_is_always_stale():
    e = FundNavEngine()
    assert e.is_stale("2025-01-01") is True
    with pytest.raises(StaleAuthorityError):
        e.nav("2025-01-01", 1)


def test_add_price_insertion_order_does_not_matter():
    e = FundNavEngine()
    for d, p in [("2025-01-03", 102.0), ("2024-12-30", 100.0), ("2025-01-02", 101.5)]:
        e.add_price(d, p)
    assert e.nav("2025-01-02", 2) == round(101.5 * 2, 4)
    assert e.nav("2025-06-01", 2) == round(102.0 * 2, 4)


def test_fractional_units_rounded_to_4dp():
    e = FundNavEngine({"prices": [("2025-01-01", 3.333333)]})
    assert e.nav("2025-01-01", 3) == round(3.333333 * 3, 4)


def test_reset_and_configure():
    e = FundNavEngine({"prices": SERIES})
    assert e.nav("2025-01-03", 1) == 102.0
    e.reset()
    assert e.is_stale("2025-01-03") is True
    e.configure({"prices": [("2025-02-01", 200.0)]})
    assert e.nav("2025-02-02", 1) == 200.0



# ---------------------------------------------------------------------------
# Reference data. Mirrors environment/data/*.csv row for row, in the in-memory
# form documented in instruction.md s.3, so the suite does not depend on the
# data directory being deployed alongside the engine.
# ---------------------------------------------------------------------------

CALENDAR = [
    {"date": "2024-01-01", "status": "HOLIDAY"},
    {"date": "2024-07-03", "status": "EARLY"},
    {"date": "2024-07-04", "status": "HOLIDAY"},
    {"date": "2024-11-28", "status": "HOLIDAY"},
    {"date": "2024-11-29", "status": "EARLY"},
    {"date": "2024-12-24", "status": "EARLY"},
    {"date": "2024-12-25", "status": "HOLIDAY"},
    {"date": "2025-01-01", "status": "HOLIDAY"},
    {"date": "2025-01-20", "status": "HOLIDAY"},
    {"date": "2025-02-17", "status": "HOLIDAY"},
    {"date": "2025-04-18", "status": "HOLIDAY"},
    {"date": "2025-05-26", "status": "HOLIDAY"},
    {"date": "2025-06-19", "status": "HOLIDAY"},
    {"date": "2025-07-03", "status": "EARLY"},
    {"date": "2025-07-04", "status": "HOLIDAY"},
    {"date": "2025-09-01", "status": "HOLIDAY"},
    {"date": "2025-11-27", "status": "HOLIDAY"},
    {"date": "2025-11-28", "status": "EARLY"},
    {"date": "2025-12-24", "status": "EARLY"},
    {"date": "2025-12-25", "status": "HOLIDAY"},
    {"date": "2026-01-01", "status": "HOLIDAY"},
    {"date": "2026-01-19", "status": "HOLIDAY"},
    {"date": "2026-02-16", "status": "HOLIDAY"},
]

OFFSETS = [
    {"start_date": "2024-03-10", "end_date": "2024-11-02", "utc_offset": "-04:00"},
    {"start_date": "2024-11-03", "end_date": "2025-03-08", "utc_offset": "-05:00"},
    {"start_date": "2025-03-09", "end_date": "2025-11-01", "utc_offset": "-04:00"},
    {"start_date": "2025-11-02", "end_date": "2026-03-07", "utc_offset": "-05:00"},
    {"start_date": "2026-03-08", "end_date": "2026-10-31", "utc_offset": "-04:00"},
]

ACTIONS = [
    {"ex_date": "2025-03-17", "announced_on": "2025-02-28", "factor": "2.0"},
    {"ex_date": "2025-04-01", "announced_on": "2025-03-12", "factor": "2.0"},
    {"ex_date": "2025-05-01", "announced_on": "2025-04-10", "factor": "0.2"},
    {"ex_date": "2026-02-02", "announced_on": "2025-12-15", "factor": "3.0"},
]

MASTER = [
    {"price_date": "2025-01-03", "published_at": "2025-01-03T16:00:00-05:00", "price": "102.00"},
    {"price_date": "2024-12-30", "published_at": "2025-01-10T08:00:00-05:00", "price": "100.25"},
    {"price_date": "2025-01-06", "published_at": "2025-01-06T16:00:00-05:00", "price": "105.00"},
    {"price_date": "2025-01-06", "published_at": "2025-01-08T09:30:00-05:00", "price": "107.50"},
    {"price_date": "2025-01-06", "published_at": "2025-01-07T11:15:00-05:00", "price": "106.00"},
    {"price_date": "2024-12-30", "published_at": "2024-12-30T16:00:00-05:00", "price": "100.00"},
    {"price_date": "2025-02-13", "published_at": "2025-02-13T16:00:00-05:00", "price": "80.00"},
    {"price_date": "2025-02-14", "published_at": "2025-02-18T09:00:00-05:00", "price": "84.00"},
    {"price_date": "2025-03-14", "published_at": "2025-03-14T16:00:00-04:00", "price": "60.00"},
    {"price_date": "2025-03-31", "published_at": "2025-03-31T16:00:00-04:00", "price": "100.00"},
    {"price_date": "2025-04-01", "published_at": "2025-04-01T16:00:00-04:00", "price": "30.50"},
    {"price_date": "2025-06-10", "published_at": "2025-06-10T16:00:00-04:00", "price": "2.71828"},
    {"price_date": "2025-06-11", "published_at": "2025-06-11T16:00:00-04:00", "price": "7.00005"},
    {"price_date": "2025-06-12", "published_at": "2025-06-12T16:00:00-04:00", "price": "55.55555"},
    {"price_date": "2025-06-13", "published_at": "2025-06-13T16:00:00-04:00", "price": "1.23450"},
    {"price_date": "2025-07-03", "published_at": "2025-07-03T13:00:00-04:00", "price": "50.00"},
    {"price_date": "2025-07-07", "published_at": "2025-07-07T16:00:00-04:00", "price": "52.00"},
    {"price_date": "2025-07-08", "published_at": "2025-07-08T16:00:00-04:00", "price": "60.00"},
    {"price_date": "2025-11-25", "published_at": "2025-11-25T16:00:00-05:00", "price": "120.00"},
]


def make_engine(prices, policy=None):
    """An engine wired to the shipped calendar, offsets and corporate actions."""
    config = {
        "prices": prices,
        "calendar": CALENDAR,
        "offsets": OFFSETS,
        "actions": ACTIONS,
    }
    if policy is not None:
        config["policy"] = policy
    return FundNavEngine(config)


def master_engine(policy=None):
    return make_engine(MASTER, policy)


# ---------------------------------------------------------------------------
# Dealing-day resolution
# ---------------------------------------------------------------------------

def test_weekend_cutoff_resolves_to_the_next_dealing_session():
    """cal-01: a cutoff on a non-session is carried forward, not back."""
    e = make_engine([("2025-01-03", 102.00), ("2025-01-06", 105.00)])
    assert e.resolve_valuation_date("2025-01-04") == dt.date(2025, 1, 6)
    assert e.nav("2025-01-04", 10) == 1050.00


def test_holiday_cutoff_resolves_to_the_next_dealing_session():
    """cal-07: a listed holiday is not a session and is carried forward."""
    e = make_engine([("2025-11-26", 90.00), ("2025-11-28", 91.00)])
    assert e.resolve_valuation_date("2025-11-27") == dt.date(2025, 11, 28)
    assert e.nav("2025-11-27", 10) == 910.00


def test_timestamp_exactly_at_the_deadline_prices_that_session():
    """cal-02: an instruction received at the deadline is in time."""
    e = make_engine([("2025-01-06", 105.00), ("2025-01-07", 108.25)])
    assert e.resolve_valuation_date("2025-01-06T16:00:00-05:00") == dt.date(2025, 1, 6)
    assert e.nav("2025-01-06T16:00:00-05:00", 100) == 10500.00


def test_timestamp_after_the_deadline_rolls_to_the_next_session():
    """cal-03: one second past the deadline prices at the following session."""
    e = make_engine([("2025-01-06", 105.00), ("2025-01-07", 108.25)])
    assert e.resolve_valuation_date("2025-01-06T16:00:01-05:00") == dt.date(2025, 1, 7)
    assert e.nav("2025-01-06T16:00:01-05:00", 100) == 10825.00


def test_early_close_session_has_an_earlier_deadline():
    """cal-04 / cal-05: an EARLY session cuts at 13:00, not 16:00."""
    prices = [("2025-07-03", 50.00), ("2025-07-07", 52.00)]
    e = make_engine(prices)
    assert e.nav("2025-07-03T13:00:00-04:00", 10) == 500.00
    assert e.resolve_valuation_date("2025-07-03T13:30:00-04:00") == dt.date(2025, 7, 7)
    assert e.nav("2025-07-03T13:30:00-04:00", 10) == 520.00


def test_cutoff_timestamp_is_converted_into_exchange_local_time():
    """cal-06: the offset in force for the session decides, not the sender's."""
    e = make_engine([("2025-07-07", 52.00), ("2025-07-08", 60.00)])
    assert e.resolve_valuation_date("2025-07-07T20:30:00+00:00") == dt.date(2025, 7, 8)
    assert e.nav("2025-07-07T20:30:00+00:00", 10) == 600.00


# ---------------------------------------------------------------------------
# Bitemporal price selection
# ---------------------------------------------------------------------------

def test_the_days_own_close_is_in_force_at_its_own_strike():
    """vin-01: a record published at the strike counts as published by it."""
    assert master_engine().nav("2025-01-06", 100) == 10500.00


def test_replay_uses_the_record_in_force_at_the_original_strike():
    """vin-02: the 07 strike sees the 07 correction, not the 08 one."""
    assert master_engine().nav("2025-01-07", 100) == 10600.00


def test_later_dealing_point_sees_the_later_correction():
    """vin-03: the correction published on 08 applies from the 08 strike on."""
    assert master_engine().nav("2025-01-09", 100) == 10750.00


def test_backdated_restatement_is_invisible_before_it_was_published():
    """vin-04: a correction for an old price date is not evidence before it exists."""
    assert master_engine().nav("2025-01-02", 10) == 1000.00


def test_backdated_restatement_applies_once_published():
    """vin-05: at a later dealing point a newer price date is in force, and the
    back-dated correction to 2024-12-30 no longer decides the answer."""
    assert master_engine().nav("2025-01-13", 10) == 1075.00


def test_price_date_published_late_falls_back_to_an_earlier_price_date():
    """vin-06 / vin-07: a price date with nothing published by the strike is
    unavailable at that dealing point, and available at a later one."""
    e = master_engine()
    assert e.nav("2025-02-14", 10) == 800.00
    assert e.nav("2025-02-19", 10) == 840.00


# ---------------------------------------------------------------------------
# Corporate-action restatement
# ---------------------------------------------------------------------------

def test_price_struck_before_an_ex_date_is_restated():
    """ca-01: a pre-split price valued after the split is divided by the factor."""
    assert master_engine().nav("2025-03-17", 100) == 3000.00


def test_forward_roll_across_an_ex_date_changes_the_restatement():
    """ca-01 vs ca-02: the Saturday cutoff crosses the ex-date; the Friday one
    does not, and the same price record gives two different position values."""
    e = master_engine()
    assert e.nav("2025-03-14", 100) == 6000.00
    assert e.nav("2025-03-15", 100) == 3000.00


def test_price_dated_on_the_ex_date_is_not_restated():
    """ca-03: the ex-date session is already priced on the post-action basis."""
    assert master_engine().nav("2025-04-01", 100) == 3050.00


def test_reverse_split_restatement_divides_by_a_fractional_factor():
    """ca-04: a factor below 1 raises the restated price, it does not lower it."""
    assert master_engine().nav("2025-05-15", 10) == 1525.00


def test_announced_action_not_yet_effective_is_not_applied():
    """ca-05: an ex-date after the valuation date is not in force."""
    assert master_engine().nav("2025-07-08", 10) == 600.00


# ---------------------------------------------------------------------------
# Publication scales
# ---------------------------------------------------------------------------

def test_position_value_is_built_from_the_published_nav_per_unit():
    """rnd-01: 2.71828 held 1000 times reconciles to 2718.30."""
    e = master_engine()
    assert e.nav_per_unit("2025-06-10") == 2.7183
    assert e.nav("2025-06-10", 1000) == 2718.30


def test_publication_ties_round_away_from_zero_at_the_unit_scale():
    """rnd-02 / rnd-03: a tie in the fifth decimal rounds up before it is applied."""
    e = master_engine()
    assert e.nav("2025-06-11", 20000) == 140002.00
    assert e.nav("2025-06-12", 40000) == 2222224.00


def test_position_value_ties_round_away_from_zero_at_the_cent_scale():
    """rnd-04: 1.2345 held 10 times reconciles to 12.35, not 12.34."""
    assert master_engine().nav("2025-06-13", 10) == 12.35


# ---------------------------------------------------------------------------
# Stale pricing authority
# ---------------------------------------------------------------------------

def test_price_age_is_counted_in_dealing_sessions():
    """stale-01: four sessions old over a holiday week is inside a five-session limit."""
    e = master_engine({"max_price_age_sessions": 5})
    assert e.is_stale("2025-12-02") is False
    assert e.nav("2025-12-02", 10) == 1200.00
    # exactly at the limit is still usable authority
    assert e.nav("2025-12-03", 10) == 1200.00


def test_price_beyond_the_age_limit_is_stale_authority():
    """stale-02: six sessions old is outside the same limit."""
    e = master_engine({"max_price_age_sessions": 5})
    assert e.is_stale("2025-12-04") is True
    with pytest.raises(StaleAuthorityError):
        e.nav("2025-12-04", 10)


def test_no_record_in_force_at_all_is_stale_authority():
    """stale-03: nothing published by the strike, at any price date."""
    e = master_engine()
    assert e.is_stale("2024-12-27") is True
    with pytest.raises(StaleAuthorityError):
        e.nav("2024-12-27", 10)


def test_price_date_only_published_later_is_stale_at_the_earlier_strike():
    """A price date whose only record lands after the strike, with nothing
    earlier to fall back to, leaves the dealing point with no authority."""
    e = make_engine([
        {"price_date": "2025-01-06", "published_at": "2025-01-06T17:05:00-05:00",
         "price": "105.00"},
    ])
    assert e.is_stale("2025-01-06") is True
    assert e.nav("2025-01-07", 100) == 10500.00


# ---------------------------------------------------------------------------
# Configuration semantics
# ---------------------------------------------------------------------------

def test_reset_clears_prices_but_keeps_the_calendar():
    """reset() drops the series; calendar, offsets and actions are configuration."""
    e = master_engine()
    e.reset()
    assert e.is_stale("2025-03-17") is True
    e.configure({"prices": [("2025-03-14", 60.00)]})
    assert e.resolve_valuation_date("2025-11-27") == dt.date(2025, 11, 28)
    assert e.nav("2025-03-17", 100) == 3000.00


def test_add_price_accepts_a_publication_instant_and_order_is_irrelevant():
    """add_price grows the bitemporal series; insertion order changes nothing."""
    e = make_engine([])
    for row in reversed(MASTER):
        e.add_price(row["price_date"], row["price"], row["published_at"])
    assert e.nav("2025-01-07", 100) == 10600.00
    assert e.nav("2025-01-09", 100) == 10750.00
