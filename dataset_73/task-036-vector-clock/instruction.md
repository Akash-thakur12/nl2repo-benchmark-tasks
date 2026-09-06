# Vector Clock — Distributed Causality Tracking

## 1. Overview

The engine **is one vector clock**: a `{node_id: counter}` mapping. Comparison
methods take the other clock as a plain dict. Standard library only; code in
`engine/`. `engine/clock.py` holds `VectorClockEntry(node_id, count)`.

## 2. Public API — `engine/engine.py`

### `class VectorClockEngine`

- `__init__(self, config=None)` — `config["node"]` optionally sets this node's id.
  The clock starts empty.
- `tick(self, node_id=None) -> dict` — increment `node_id` (default: the
  configured node). Raises `ValueError` if no id is available. Returns the clock.
- `set(self, node_id, value)` / `get(self, node_id) -> int` (0 if absent).
- `to_dict(self) -> dict` — a copy of the clock.
- `merge(self, other: dict) -> dict` — component-wise `max` into this clock
  (idempotent and commutative).
- `gc(self, live_nodes) -> dict` — drop entries whose node is not in
  `live_nodes` (tombstone garbage collection).
- `happens_before(self, other: dict) -> bool` — strict causal precedence.
- `descendant(self, other: dict) -> bool` — this clock is `>=` `other`
  component-wise (happened-after **or** equal).
- `is_concurrent(self, other: dict) -> bool` — neither precedes the other.
- `compare(self, other: dict) -> str` — one of `"equal"`, `"before"`, `"after"`,
  `"concurrent"`.
- `__eq__` — compares against another engine or a `{node_id: counter}` dict;
  missing entries count as 0.
- `reset(self)` — empty the clock (keeps the configured node).
- `configure(self, options)` — set `node` from `options` and empty the clock.

## 3. Example

```python
a = VectorClockEngine({"node": "a"}); a.tick()          # {"a": 1}
b = VectorClockEngine({"node": "b"})
b.merge(a.to_dict()); b.tick()                            # {"a": 1, "b": 1}
a.happens_before(b.to_dict())                             # -> True
b.is_concurrent({"a": 0, "c": 1})                          # -> True
```

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
