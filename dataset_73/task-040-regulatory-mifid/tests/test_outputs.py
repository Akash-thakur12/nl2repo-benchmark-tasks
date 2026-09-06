import pytest
from engine.engine import MifidEngine


VALID = {
    "LEI": "529900T8BM49AURSDO55",
    "ISIN": "US0378331005",
    "VENUE": "XNAS",
    "CAPACITY": "DEAL",
    "PRICE": 150.0,
    "QTY": 10,
    "TS": "2024-01-15T09:30:00",
    "SIDE": "BUY",
}


@pytest.fixture
def e():
    return MifidEngine()


def test_valid_record_has_no_errors(e):
    assert e.validate(VALID) == []


def test_missing_fields_reported(e):
    errs = e.validate({"LEI": VALID["LEI"], "ISIN": VALID["ISIN"]})
    assert any(x.startswith("missing:") for x in errs)
    assert "missing:VENUE" in errs and "missing:SIDE" in errs


@pytest.mark.parametrize("field,bad", [
    ("SIDE", "HOLD"),
    ("CAPACITY", "XXXX"),
    ("TS", "15/01/2024"),
    ("PRICE", 0),
    ("PRICE", -3.5),
    ("QTY", 0),
    ("QTY", -1),
    ("VENUE", "ZZZZ"),
])
def test_single_bad_field(e, field, bad):
    errs = e.validate({**VALID, field: bad})
    assert errs == [f"bad:{field}"]


def test_lei_checksum(e):
    assert e.validate({**VALID, "LEI": "X" * 20}) == ["bad:LEI"]
    assert e.validate({**VALID, "LEI": "529900T8BM49AURSDO54"}) == ["bad:LEI"]
    assert e.validate({**VALID, "LEI": "TOO-SHORT"}) == ["bad:LEI"]


def test_isin_luhn(e):
    assert e.validate({**VALID, "ISIN": "US0378331006"}) == ["bad:ISIN"]   # wrong check digit
    assert e.validate({**VALID, "ISIN": "GB0002634946"}) == []            # valid ISIN
    assert e.validate({**VALID, "ISIN": "US037833100"}) == ["bad:ISIN"]   # too short


def test_multiple_errors_accumulate(e):
    errs = e.validate({**VALID, "SIDE": "X", "PRICE": -1, "VENUE": "ZZZZ"})
    assert set(errs) == {"bad:SIDE", "bad:PRICE", "bad:VENUE"}


def test_extra_fields_are_ignored(e):
    assert e.validate({**VALID, "TRADER_NOTE": "n/a", "FLAGS": ["ALGO"]}) == []


def test_bool_is_not_a_valid_price(e):
    assert e.validate({**VALID, "PRICE": True}) == ["bad:PRICE"]


def test_bool_is_not_a_valid_qty(e):
    assert e.validate({**VALID, "QTY": True}) == ["bad:QTY"]
    assert e.validate({**VALID, "QTY": False}) == ["bad:QTY"]


def test_hash_report(e):
    h = e.hash_report(VALID)
    assert isinstance(h, str) and len(h) == 64
    assert e.hash_report(VALID) == h                       # stable
    assert e.hash_report({**VALID, "QTY": 11}) != h        # sensitive
    assert e.hash_report({**VALID, "SIDE": "SELL"}) != h


@pytest.mark.parametrize("record,ok", [
    (VALID, True),
    ({**VALID, "LEI": "SHORT"}, False),
    ({**VALID, "CAPACITY": "DEAL"}, True),
])
def test_matrix(e, record, ok):
    assert (e.validate(record) == []) is ok


def test_reset_and_configure_are_noops(e):
    ref = e.validate(VALID)
    e.reset()
    assert e.validate(VALID) == ref
    e.configure({})
    assert e.validate(VALID) == ref
