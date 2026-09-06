from __future__ import annotations

import hmac


def safe_compare(a, b) -> bool:
    """Constant-time equality (thin wrapper over hmac.compare_digest)."""
    if isinstance(a, str):
        a = a.encode()
    if isinstance(b, str):
        b = b.encode()
    return hmac.compare_digest(a, b)


def naive_compare(a, b) -> bool:
    """Deliberately vulnerable: returns on the first differing byte."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x != y:
            return False
    return True
