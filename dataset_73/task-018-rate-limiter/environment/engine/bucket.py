from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class TokenBucket:
    """Leaky token bucket with a caller-supplied clock.

    See instruction.md for the API and ../docs/limiter-contract.md for the
    policy-row and clock rules the bucket has to live with. Extra optional
    constructor parameters are allowed; ``capacity``, ``refill_rate`` and
    ``now`` are not.
    """

    def __init__(self, capacity: float, refill_rate: float, now: float):
        raise NotImplementedError(_STUB)

    def take(self, cost: float, now: float) -> bool:
        raise NotImplementedError(_STUB)

    def level(self, now: float) -> float:
        raise NotImplementedError(_STUB)
