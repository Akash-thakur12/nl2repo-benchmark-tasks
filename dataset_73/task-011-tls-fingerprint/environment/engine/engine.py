from __future__ import annotations

import hashlib
import struct

_STUB = "Stub for NL2Repo evaluation: implementation required."


class ValidationError(ValueError):
    pass


class TlsFingerprintEngine:
    """Parse a TLS ClientHello and compute a simplified JA3. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse(self, raw):
        raise NotImplementedError(_STUB)
