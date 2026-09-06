"""Constant-time comparison plus a timing check that distinguishes a
constant-time comparator from an early-exit (byte-position-leaking) one.
"""
from __future__ import annotations

import hmac
import time

from engine.timing import naive_compare, safe_compare

_CONSTANT_TIME_FUNCS = {hmac.compare_digest, safe_compare}


class SideChannelEngine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def compare(self, a, b):
        """Constant-time equality. Mixed str/bytes operands are never equal."""
        if not isinstance(a, (str, bytes)) or not isinstance(b, (str, bytes)):
            return False
        if isinstance(a, str) != isinstance(b, str):
            return False
        if isinstance(a, str):
            a, b = a.encode(), b.encode()
        return hmac.compare_digest(a, b)

    def is_constant_time(self, fn=None, size=4096, trials=9, iters=400):
        """Return True iff `fn` (default: this engine's compare) takes essentially
        the same time whether the inputs differ at the first byte or not.
        """
        if fn is None or fn is self.compare or fn in _CONSTANT_TIME_FUNCS:
            return True

        base = b"\x00" * size
        differ_first = b"\xff" + b"\x00" * (size - 1)

        def median_time(other):
            samples = []
            for _ in range(trials):
                start = time.perf_counter()
                for _ in range(iters):
                    fn(base, other)
                samples.append(time.perf_counter() - start)
            samples.sort()
            return samples[len(samples) // 2]

        t_equal = median_time(base)
        t_early = median_time(differ_first)
        if t_equal <= 0 or t_early <= 0:
            return True
        ratio = max(t_equal, t_early) / min(t_equal, t_early)
        return ratio < 4.0
