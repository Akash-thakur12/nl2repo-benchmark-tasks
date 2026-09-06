from __future__ import annotations

import re

#: JWK key type families that are asymmetric. Presenting one of these to an
#: HMAC algorithm is the RS256 -> HS256 key-confusion attack.
#: See environment/docs/key-confusion-policy.md.
ASYMMETRIC_KTY = frozenset({"RSA", "EC", "OKP"})

#: The HMAC (symmetric) signature algorithm family.
HMAC_ALGS = frozenset({"HS256", "HS384", "HS512"})

#: The kty is the LEADING run of alphanumeric characters of the operator's
#: key description; everything after it is unstructured prose and carries no
#: policy meaning (so "HMAC key wrapped by RSA KEK" has kty "HMAC", not "RSA").
_LEADING_TOKEN = re.compile(r"[A-Za-z0-9]+")


def key_type_family(key_type: str) -> str:
    """The JWK ``kty`` named by an operator-written key description, upper-cased.

    Empty string when the description does not begin with a word.
    """
    if not key_type:
        return ""
    found = _LEADING_TOKEN.match(key_type.strip())
    return found.group(0).upper() if found else ""


def detect_key_confusion(header_alg: str, key_type: str) -> bool:
    """True iff an HMAC-family alg is being presented with an asymmetric key."""
    if header_alg not in HMAC_ALGS:
        return False
    return key_type_family(key_type) in ASYMMETRIC_KTY
