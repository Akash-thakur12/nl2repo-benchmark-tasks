"""Onion-routing relay cell processing.

Layered stream cipher (SHA-256 in counter mode, standard library only), fixed
498-byte cell payloads, and "recognized vs relay-forward" classification.
"""
from __future__ import annotations

import hashlib

from engine.cells import CELL_PAYLOAD_LEN, LEN_FIELD, RECOGNIZED_MARKER


def _keystream(key: bytes, nbytes: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        out += hashlib.sha256(key + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:nbytes])


def _apply(key: bytes, data: bytes) -> bytes:
    ks = _keystream(key, len(data))
    return bytes(a ^ b for a, b in zip(data, ks))


class TorRelayEngine:
    def __init__(self, config=None):
        self._keys = {}
        self.reset()

    def reset(self):
        self._seen = set()

    def configure(self, options):
        self._keys = {}
        self._seen = set()

    def register_circuit(self, circ_id, hop, key):
        self._keys[(circ_id, hop)] = key

    # ------------------------------------------------------------ one layer
    def make_cell(self, circ_id, hop, payload):
        key = self._keys.get((circ_id, hop))
        if key is None:
            raise ValueError(f"no key for circuit {circ_id} hop {hop}")
        if len(payload) > CELL_PAYLOAD_LEN - len(RECOGNIZED_MARKER) - LEN_FIELD:
            raise ValueError("payload too large for one cell")
        header = RECOGNIZED_MARKER + len(payload).to_bytes(LEN_FIELD, "big")
        plain = header + payload
        plain = plain + b"\x00" * (CELL_PAYLOAD_LEN - len(plain))
        return _apply(key, plain)

    def decrypt(self, circ_id, hop, cell):
        key = self._keys.get((circ_id, hop))
        if key is None:
            return None
        plain = _apply(key, cell)
        if plain[: len(RECOGNIZED_MARKER)] != RECOGNIZED_MARKER:
            return None
        start = len(RECOGNIZED_MARKER)
        length = int.from_bytes(plain[start:start + LEN_FIELD], "big")
        end = start + LEN_FIELD + length
        if end > len(plain):
            return None
        self._seen.add((circ_id, hop))
        return RECOGNIZED_MARKER + plain[start + LEN_FIELD:end]

    def recognized(self, circ_id, hop):
        return (circ_id, hop) in self._seen

    # --------------------------------------------------------- multi-hop
    def make_onion(self, circ_id, hops, payload):
        """Wrap `payload` for a path of hops; outermost layer is hops[0]."""
        cell = self.make_cell(circ_id, hops[-1], payload)
        for hop in reversed(hops[:-1]):
            key = self._keys.get((circ_id, hop))
            if key is None:
                raise ValueError(f"no key for circuit {circ_id} hop {hop}")
            cell = _apply(key, cell)
        return cell

    def peel(self, circ_id, hops, cell):
        """Peel every hop's layer in order; return the recognized payload or None."""
        for hop in hops[:-1]:
            key = self._keys.get((circ_id, hop))
            if key is None:
                return None
            cell = _apply(key, cell)
        return self.decrypt(circ_id, hops[-1], cell)
