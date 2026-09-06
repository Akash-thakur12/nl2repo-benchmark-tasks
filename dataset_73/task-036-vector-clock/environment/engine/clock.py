from __future__ import annotations


class VectorClockEntry:
    """One (node, counter) pair."""

    __slots__ = ("node_id", "count")

    def __init__(self, node_id: str, count: int = 0):
        self.node_id = node_id
        self.count = count

    def __repr__(self):
        return f"VectorClockEntry({self.node_id!r}, {self.count})"
