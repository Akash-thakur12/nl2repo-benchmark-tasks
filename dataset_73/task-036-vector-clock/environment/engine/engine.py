from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class VectorClockEngine:
    """A single vector clock for causality tracking. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def tick(self, node_id=None):
        raise NotImplementedError(_STUB)

    def set(self, node_id, value):
        raise NotImplementedError(_STUB)

    def get(self, node_id):
        raise NotImplementedError(_STUB)

    def to_dict(self):
        raise NotImplementedError(_STUB)

    def merge(self, other):
        raise NotImplementedError(_STUB)

    def gc(self, live_nodes):
        raise NotImplementedError(_STUB)

    def happens_before(self, other):
        raise NotImplementedError(_STUB)

    def descendant(self, other):
        raise NotImplementedError(_STUB)

    def is_concurrent(self, other):
        raise NotImplementedError(_STUB)

    def compare(self, other):
        raise NotImplementedError(_STUB)
