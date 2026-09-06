from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class TorRelayEngine:
    """Onion-routing relay cell processor. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def register_circuit(self, circ_id, hop, key):
        raise NotImplementedError(_STUB)

    def make_cell(self, circ_id, hop, payload):
        raise NotImplementedError(_STUB)

    def decrypt(self, circ_id, hop, cell):
        raise NotImplementedError(_STUB)

    def recognized(self, circ_id, hop):
        raise NotImplementedError(_STUB)

    def make_onion(self, circ_id, hops, payload):
        raise NotImplementedError(_STUB)

    def peel(self, circ_id, hops, cell):
        raise NotImplementedError(_STUB)
