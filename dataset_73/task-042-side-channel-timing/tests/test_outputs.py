import hmac

import pytest
from engine.engine import SideChannelEngine
from engine.timing import naive_compare, safe_compare


@pytest.fixture
def e():
    return SideChannelEngine()


@pytest.mark.parametrize("a,b,expected", [
    ("secret123", "secret123", True),
    ("secret123", "s3cret123", False),
    ("longsecret", "longsecret", True),
    ("longsecret", "longsecreX", False),
    ("", "", True),
    ("a", "ab", False),
])
def test_compare_result(e, a, b, expected):
    assert e.compare(a, b) is expected


def test_compare_bytes(e):
    assert e.compare(b"abc", b"abc") is True
    assert e.compare(b"abc", b"abd") is False


def test_compare_mixed_types_never_equal(e):
    assert e.compare("abc", b"abc") is False
    assert e.compare(b"abc", "abc") is False
    assert e.compare("abc", 123) is False
    assert e.compare(None, None) is False


def test_default_and_known_safe_functions_are_constant_time(e):
    assert e.is_constant_time() is True
    assert e.is_constant_time(e.compare) is True
    assert e.is_constant_time(safe_compare) is True
    assert e.is_constant_time(hmac.compare_digest) is True


def test_naive_early_exit_comparator_is_rejected(e):
    assert e.is_constant_time(naive_compare) is False



def test_reset_and_configure(e):
    assert e.is_constant_time() is True
    e.reset()
    assert e.compare("x", "x") is True
    e.configure({})
    assert e.is_constant_time(safe_compare) is True


def test_one_operand_of_the_wrong_type_is_enough(e):
    """Both operands have to be strings or bytes. One of the right type does
    not excuse the other, and a wrong type is answered with False rather than
    an exception."""
    assert e.compare(b"abc", 123) is False
    assert e.compare(123, b"abc") is False
    assert e.compare("abc", None) is False
    assert e.compare(None, "abc") is False
    assert e.compare(None, 123) is False


def test_both_probes_are_the_full_size(e):
    """The two probes must be the same length, or the timing difference would
    measure the length rather than the comparison. Both are `size` bytes: one
    all zeros, one differing at the very first byte."""
    seen = []

    def watcher(a, b):
        seen.append((len(a), len(b), b[:1]))
        return a == b

    e.is_constant_time(watcher, size=64, trials=3, iters=2)
    assert seen, "the probe function was never called"
    assert all(x == 64 and y == 64 for x, y, _ in seen), \
        "both probes must be exactly `size` bytes long"
    assert {first for _, _, first in seen} == {b"\x00", b"\xff"}, \
        "one probe matches from the first byte, the other differs there"
