import datetime as dt

import pytest
from engine.engine import CronParserEngine


@pytest.fixture
def e():
    return CronParserEngine()


def test_parse_5_field(e):
    r = e.parse("*/15 * * * *")
    assert r["minute"] == [0, 15, 30, 45]
    assert r["hour"] == list(range(24))


def test_parse_6_field(e):
    r = e.parse("0 0 12 * * *")
    assert r["second"] == [0] and r["hour"] == [12]


def test_parse_7_field(e):
    assert e.parse("0 0 0 1 1 * 2025")["year"] == [2025]


def test_range_and_list(e):
    assert e.parse("0 9-17 * * *")["hour"] == list(range(9, 18))
    assert e.parse("0 0,6,12,18 * * *")["hour"] == [0, 6, 12, 18]


def test_step_over_range(e):
    assert e.parse("0 0 1-15/5 * *")["dom"] == [1, 6, 11]


def test_dow_seven_normalises_to_zero(e):
    assert e.parse("0 12 * * 7")["dow"] == [0]
    assert e.parse("0 12 * * 0,7")["dow"] == [0]


@pytest.mark.parametrize("bad", [
    "0 99 0 0 0",        # hour out of range
    "* * * *",           # wrong field count
    "* * * * * * * *",   # too many fields
    "*/0 * * * *",       # zero step
    "5-1 * * * *",       # inverted range
    "1,,2 * * * *",      # empty list element
    "0 0 32 * *",        # day of month out of range
])
def test_invalid_raises(e, bad):
    with pytest.raises(ValueError):
        e.parse(bad)


def test_next_after_simple(e):
    # Monday 2025-01-06 08:50 -> next */15 at hour 9 on a weekday
    assert e.next_after("*/15 9 * * 1-5", "2025-01-06T08:50:00") == "2025-01-06T09:00:00"


def test_next_after_month_rollover(e):
    assert e.next_after("0 0 1 * *", "2025-01-15T00:00:00") == "2025-02-01T00:00:00"


def test_next_after_weekday_only(e):
    # from a Wednesday, next Sunday-noon
    result = e.next_after("0 12 * * 0", "2025-01-15T00:00:00")
    got = dt.datetime.fromisoformat(result)
    assert got == dt.datetime(2025, 1, 19, 12, 0, 0)
    assert (got.weekday() + 1) % 7 == 0


def test_next_after_dom_or_dow_semantics(e):
    # "13th of the month OR any Friday" -> first Friday on/after 2025-06-02
    assert e.next_after("0 0 13 * 5", "2025-06-01T00:00:00") == "2025-06-06T00:00:00"


def test_next_after_is_strictly_after(e):
    # already at a matching minute -> returns the *next* one
    assert e.next_after("* * * * *", "2025-01-01T00:00:00") == "2025-01-01T00:01:00"


def test_next_after_with_seconds(e):
    assert e.next_after("*/30 * * * * *", "2025-01-01T00:00:05") == "2025-01-01T00:00:30"


def test_next_after_no_match_raises(e):
    # month 2 + day 30 never occurs
    with pytest.raises(ValueError):
        e.next_after("0 0 30 2 *", "2025-01-01T00:00:00")


@pytest.mark.parametrize("expr", [
    "* * * * *", "0 0 * * *", "0 0 1 * *", "0 0 1 1 *",
    "*/5 * * * *", "0 9-17 * * 1-5",
])
def test_parse_matrix(e, expr):
    r = e.parse(expr)
    assert "minute" in r and isinstance(r["minute"], list)


def test_reset_and_configure_are_noops(e):
    ref = e.parse("*/15 9 * * 1-5")
    e.reset()
    assert e.parse("*/15 9 * * 1-5") == ref
    e.configure({})
    assert e.parse("*/15 9 * * 1-5") == ref
