from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class WriteAheadLog:
    """Append-only durability log, one JSON record per line. See instruction.md."""

    def __init__(self, filepath: str):
        raise NotImplementedError(_STUB)

    def append(self, record) -> None:
        raise NotImplementedError(_STUB)

    def replay(self):
        raise NotImplementedError(_STUB)

    def truncate(self) -> None:
        raise NotImplementedError(_STUB)

    def close(self) -> None:
        raise NotImplementedError(_STUB)
