import pytest
from engine.engine import JsonParserEngine, JSONDecodeError


@pytest.fixture
def e():
    return JsonParserEngine()


def test_object(e):
    assert e.parse('{"a":1}') == {"a": 1}


def test_array(e):
    assert e.parse('[1,2,3]') == [1, 2, 3]


def test_nested(e):
    assert e.parse('{"a":[1,{"b":true}],"c":null}') == {"a": [1, {"b": True}], "c": None}


def test_empty_containers(e):
    assert e.parse('{}') == {} and e.parse('[]') == []


def test_scalars(e):
    assert e.parse('true') is True
    assert e.parse('false') is False
    assert e.parse('null') is None
    assert e.parse('"hi"') == "hi"


def test_string_escapes(e):
    assert e.parse('"a\\nb\\tc"') == "a\nb\tc"
    assert e.parse('"quote:\\" slash:\\/ back:\\\\"') == 'quote:" slash:/ back:\\'


def test_string_escapes_backspace_formfeed_return(e):
    assert e.parse('"\\b"') == "\b"
    assert e.parse('"\\f"') == "\f"
    assert e.parse('"\\r"') == "\r"
    assert e.parse('"x\\by\\fz\\r"') == "x\by\fz\r"


def test_unicode_escape(e):
    assert e.parse('"\\u0041\\u00e9"') == "Aé"


def test_surrogate_pair(e):
    assert e.parse('"\\uD83D\\uDE00"') == "\U0001F600"


def test_numbers(e):
    assert e.parse('0') == 0
    assert e.parse('-5') == -5
    assert e.parse('3.14') == 3.14
    assert e.parse('1e10') == 1e10
    assert e.parse('-0.5E2') == -50.0
    assert isinstance(e.parse('42'), int)
    assert isinstance(e.parse('42.0'), float)


def test_bigint(e):
    assert e.parse('12345678901234567890') == 12345678901234567890


def test_whitespace_tolerated(e):
    assert e.parse('  {  "a" : [ 1 , 2 ]  }  ') == {"a": [1, 2]}


def test_tokens_schema(e):
    t = e.tokens('{"a":1,"b":true,"c":null}')
    assert t == ["{", ("STRING", "a"), ":", ("NUMBER", "1"), ",",
                 ("STRING", "b"), ":", ("BOOL", True), ",",
                 ("STRING", "c"), ":", ("NULL", None), "}"]


@pytest.mark.parametrize("bad", [
    "{bad}",
    '{"a":1,}',           # trailing comma
    "[1,2,]",
    '{"a"1}',             # missing colon
    "01",                 # leading zero
    "1.",                 # no fraction digits
    ".1",                 # no integer part
    "+1",                 # leading plus
    "nul",               # bad literal
    '{"a":}',             # missing value
    "[",                 # unterminated
    '{"a":1}extra',       # trailing data
    "'single'",          # single quotes
    "{,}",
    '"\\x"',             # bad escape
    '"unterminated',
    "",
])
def test_invalid_raises(e, bad):
    with pytest.raises(ValueError):
        e.parse(bad)


def test_deep_nesting_is_rejected(e):
    payload = "[" * 500 + "]" * 500
    with pytest.raises(ValueError):
        e.parse(payload)


@pytest.mark.parametrize("s", ['{}', '[]', '{"a":1}', '[1,2,3]', '"x"', 'true', 'null', '3.14'])
def test_matrix(e, s):
    e.parse(s)


def test_reset_and_configure(e):
    ref = e.parse('{"a":[1,2,3]}')
    e.reset()
    assert e.parse('{"a":[1,2,3]}') == ref
    e.configure({})
    assert e.parse('{"a":[1,2,3]}') == ref


def test_literal_control_char_in_string_rejected(e):
    with pytest.raises(ValueError):
        e.parse('"a\x01b"')                 # raw control char
    with pytest.raises(ValueError):
        e.parse('{"k": "line1\nline2"}')    # raw newline inside a string
    with pytest.raises(ValueError):
        e.parse('"tab\there"')
