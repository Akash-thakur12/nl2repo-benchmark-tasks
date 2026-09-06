"""A single vector clock (Lamport / Fidge-Mattern) for causality tracking.

The engine *is* one clock. All comparison methods take the other clock as a
plain ``{node_id: counter}`` dict.
"""
from __future__ import annotations


class VectorClockEngine:
    def __init__(self, config=None):
        cfg = config or {}
        self._node = cfg.get("node")
        self._clock = {}

    def reset(self):
        self._clock = {}

    def configure(self, options):
        options = options or {}
        self._node = options.get("node", self._node)
        self._clock = {}

    # ------------------------------------------------------------ mutation
    def tick(self, node_id=None):
        node_id = node_id or self._node
        if node_id is None:
            raise ValueError("no node id: pass one or set config['node']")
        self._clock[node_id] = self._clock.get(node_id, 0) + 1
        return dict(self._clock)

    def set(self, node_id, value):
        self._clock[node_id] = value

    def get(self, node_id):
        return self._clock.get(node_id, 0)

    def to_dict(self):
        return dict(self._clock)

    def merge(self, other):
        for n, v in other.items():
            if v > self._clock.get(n, 0):
                self._clock[n] = v
        return dict(self._clock)

    def gc(self, live_nodes):
        live = set(live_nodes)
        self._clock = {n: v for n, v in self._clock.items() if n in live}
        return dict(self._clock)

    # ---------------------------------------------------------- comparison
    @staticmethod
    def _leq(a, b):
        nodes = set(a) | set(b)
        return all(a.get(n, 0) <= b.get(n, 0) for n in nodes)

    def happens_before(self, other):
        return self.compare(other) == "before"

    def descendant(self, other):
        """True if this clock is >= `other` component-wise (happened-after or equal)."""
        return self._leq(other, self._clock)

    def is_concurrent(self, other):
        return not self._leq(self._clock, other) and not self._leq(other, self._clock)

    def compare(self, other):
        a, b = self._clock, other
        le_ab = self._leq(a, b)
        le_ba = self._leq(b, a)
        if le_ab and le_ba:
            return "equal"
        if le_ab:
            return "before"
        if le_ba:
            return "after"
        return "concurrent"

    def __eq__(self, other):
        if isinstance(other, VectorClockEngine):
            other = other._clock
        if not isinstance(other, dict):
            return NotImplemented
        nodes = set(self._clock) | set(other)
        return all(self._clock.get(n, 0) == other.get(n, 0) for n in nodes)

    def __repr__(self):
        return f"VectorClockEngine({self._clock!r})"
