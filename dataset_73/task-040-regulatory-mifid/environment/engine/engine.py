from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class MifidEngine:
    """MiFID II RTS 22 transaction-report validator. See instruction.md."""

    REQUIRED = ["LEI", "ISIN", "VENUE", "CAPACITY", "PRICE", "QTY", "TS", "SIDE"]
    SIDES = {"BUY", "SELL"}
    CAPS = {"DEAL", "MTCH", "AOTC"}

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def validate(self, record):
        raise NotImplementedError(_STUB)

    def hash_report(self, record):
        raise NotImplementedError(_STUB)
