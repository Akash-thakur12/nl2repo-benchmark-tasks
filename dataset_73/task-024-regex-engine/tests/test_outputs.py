import time

import pytest
from engine.engine import RegexEngine
from engine.nfa import RegexSyntaxError


@pytest.fixture
def e():
    return RegexEngine()


@pytest.mark.parametrize("pattern,text,expected", [
    # literals & dot
    ("abc", "abc", True), ("abc", "ab", False), ("abc", "xabcy", True),
    ("a.c", "axc", True), ("a.c", "ac", False),
    # star / plus / opt
    ("ab*c", "ac", True), ("ab*c", "abbbbc", True),
    ("ab+c", "abc", True), ("ab+c", "ac", False),
    ("a*", "", True), ("a*", "aaa", True),
    ("colou?r", "color", True), ("colou?r", "colour", True), ("colou?r", "colouur", False),
    # anchors
    ("^a+b*$", "aaabb", True), ("^abc$", "abc", True), ("^abc$", "xabc", False),
    ("abc$", "xabc", True), ("^abc", "abcx", True), ("^abc", "xabc", False),
    # grouping + alternation
    ("(ab)+", "ababab", True), ("(ab)+", "aba", True),
    ("(a|b)c", "ac", True), ("(a|b)c", "bc", True), ("(a|b)c", "cc", False),
    ("gr(a|e)y", "grey", True), ("gr(a|e)y", "gray", True), ("gr(a|e)y", "groy", False),
    ("a(b|c)*d", "ad", True), ("a(b|c)*d", "abccbd", True), ("a(b|c)*d", "abxd", False),
    # character classes
    ("[a-z]+", "hello", True), ("[a-z]+", "HELLO", False),
    ("[^0-9]+", "abc", True), ("[^0-9]", "5", False),
    ("[abc]", "b", True), ("[abc]", "d", False),
    ("[A-Za-z0-9]+", "Ab9", True),
    # empty pattern
    ("", "", True), ("", "abc", True),
])
def test_match_matrix(e, pattern, text, expected):
    assert e.match(pattern, text) is expected


def test_alternation_of_more_than_two(e):
    assert e.match("^(cat|dog|bird)$", "dog") is True
    assert e.match("^(cat|dog|bird)$", "fish") is False


def test_nested_groups_and_quantifiers(e):
    assert e.match("^((ab)+c)+$", "ababcabc") is True
    assert e.match("^((ab)+c)+$", "abcab") is False


def test_negated_class_with_range(e):
    assert e.match("^[^a-c]+$", "xyz") is True
    assert e.match("^[^a-c]+$", "xbz") is False


@pytest.mark.parametrize("bad", ["(", ")", "(a", "a)", "*a", "+b", "[a-", "[abc", "a\\"])
def test_invalid_pattern_raises(e, bad):
    with pytest.raises(RegexSyntaxError):
        e.match(bad, "anything")


def test_no_catastrophic_backtracking(e):
    start = time.time()
    assert e.match("^(a*)*b$", "a" * 80) is False
    assert time.time() - start < 1.0        # linear NFA sim, not exponential


def test_reset_and_configure(e):
    assert e.match("a+", "aaa") is True
    e.reset()
    assert e.match("a+", "aaa") is True
    e.configure({})
    assert e.match("a+", "aaa") is True


def test_escaped_literal_metacharacter(e):
    assert e.match(r"a\.b", "a.b") is True
    assert e.match(r"a\.b", "axb") is False       # '.' is now a literal, not "any"
    assert e.match(r"\*\+", "*+") is True
    assert e.match(r"a\(b\)", "a(b)") is True
