import pytest
from engine.engine import VectorClockEngine


def test_tick_with_configured_node():
    e = VectorClockEngine({"node": "n1"})
    e.tick()
    e.tick()
    assert e.get("n1") == 2 and e.to_dict() == {"n1": 2}


def test_tick_explicit_node():
    e = VectorClockEngine()
    e.tick("a")
    e.tick("b")
    e.tick("a")
    assert e.to_dict() == {"a": 2, "b": 1}


def test_tick_without_node_raises():
    with pytest.raises(ValueError):
        VectorClockEngine().tick()


def test_get_missing_is_zero():
    assert VectorClockEngine().get("nobody") == 0


def test_set_and_to_dict():
    e = VectorClockEngine()
    e.set("x", 7)
    assert e.get("x") == 7 and e.to_dict() == {"x": 7}


def test_merge_takes_componentwise_max():
    e = VectorClockEngine()
    e.set("a", 3)
    e.set("b", 1)
    e.merge({"a": 2, "b": 5, "c": 4})
    assert e.to_dict() == {"a": 3, "b": 5, "c": 4}


def test_merge_is_idempotent_and_commutative():
    m1 = VectorClockEngine()
    m1.merge({"a": 1, "b": 2})
    m1.merge({"a": 1, "b": 2})
    m2 = VectorClockEngine()
    m2.merge({"b": 2})
    m2.merge({"a": 1})
    assert m1.to_dict() == m2.to_dict() == {"a": 1, "b": 2}


def test_happens_before_and_descendant():
    a = VectorClockEngine()
    a.set("n1", 1)
    b = VectorClockEngine()
    b.set("n1", 2)
    assert a.happens_before(b.to_dict()) is True
    assert b.happens_before(a.to_dict()) is False
    assert b.descendant(a.to_dict()) is True
    assert a.descendant(b.to_dict()) is False


def test_concurrent_clocks():
    a = VectorClockEngine()
    a.set("n1", 1)
    a.set("n2", 0)
    b = VectorClockEngine()
    b.set("n1", 0)
    b.set("n2", 1)
    assert a.is_concurrent(b.to_dict()) is True
    assert b.is_concurrent(a.to_dict()) is True


def test_compare_all_relations():
    a = VectorClockEngine()
    a.set("x", 1)
    a.set("y", 1)
    assert a.compare({"x": 1, "y": 1}) == "equal"
    assert a.compare({"x": 2, "y": 1}) == "before"
    assert a.compare({"x": 0, "y": 1}) == "after"
    assert a.compare({"x": 2, "y": 0}) == "concurrent"


def test_equality_against_dict_and_engine():
    a = VectorClockEngine()
    a.set("n1", 3)
    assert a == {"n1": 3}
    assert a == {"n1": 3, "n2": 0}
    b = VectorClockEngine()
    b.set("n1", 3)
    assert a == b
    b.tick("n1")
    assert a != b


def test_tombstone_gc():
    e = VectorClockEngine()
    e.set("dead-node", 5)
    e.set("live-1", 2)
    e.set("live-2", 3)
    e.gc(["live-1", "live-2"])
    assert e.to_dict() == {"live-1": 2, "live-2": 3}


def test_causal_chain():
    a = VectorClockEngine({"node": "a"})
    a.tick()                         # {a:1}
    b = VectorClockEngine({"node": "b"})
    b.merge(a.to_dict())
    b.tick()                         # {a:1, b:1}
    c = VectorClockEngine({"node": "c"})
    c.merge(b.to_dict())
    c.tick()                         # {a:1, b:1, c:1}
    assert a.happens_before(b.to_dict())
    assert b.happens_before(c.to_dict())
    assert a.happens_before(c.to_dict())
    assert c.descendant(a.to_dict())


def test_reset_and_configure():
    e = VectorClockEngine({"node": "n1"})
    e.tick()
    e.reset()
    assert e.to_dict() == {}
    e.tick()                         # node still "n1"
    e.configure({"node": "n2"})
    assert e.to_dict() == {}
    e.tick()
    assert e.to_dict() == {"n2": 1}
