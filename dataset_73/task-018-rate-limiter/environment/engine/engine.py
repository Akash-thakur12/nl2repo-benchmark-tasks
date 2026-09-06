from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class RateLimiterEngine:
    """Per-key token bucket + per-key sliding window.

    See instruction.md for the API, ../docs/limiter-contract.md for the key
    format and the control-plane row shape, and ../capture/ for the recorded
    gateway behaviour the implementation has to reproduce.
    """

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def allow(self, key, cost=1):
        raise NotImplementedError(_STUB)

    def tokens(self, key):
        raise NotImplementedError(_STUB)

    def sliding_window(self, key, window_sec, max_reqs):
        raise NotImplementedError(_STUB)
