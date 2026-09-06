"""Reference implementation of the JWT security gateway.

Standard library only. Everything the gateway needs is baked in here; the
files under ``config/`` and ``samples/`` in the shipped image are evidence for
whoever has to rebuild this, not runtime inputs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

#: The algorithms an operator is allowed to pin, and the digest each one means.
#: A pin that is not a key of this table is ignored (see ``configure``).
_DIGESTS = {
    "HS256": hashlib.sha256,
    "HS384": hashlib.sha384,
    "HS512": hashlib.sha512,
}

#: Header ``alg`` values that are rejected outright, matched case-folded and
#: whitespace-stripped. Everything else is matched byte-exact against the pin.
_NEVER_ACCEPT = frozenset({"none"})

#: The edge fleet is NTP-disciplined to +/-60s. The slack is spent on the key
#: rotation windows only; it is deliberately NOT spent on token lifetime.
LEEWAY = 60

DEFAULT_KEY = b"topsecret-key"
DEFAULT_ALG = "HS256"


class GatewayError(Exception):
    """Base for the two rejection classes. Carries a stable reason ``code``."""

    def __init__(self, code, message=None):
        super().__init__(message or code)
        self.code = code


class ValidationError(GatewayError):
    """The token is structurally damaged; nothing could be decided about it."""


class UnauthorizedError(GatewayError):
    """The token decoded, and policy or authentication says no."""


def b64d(b):
    if isinstance(b, str):
        b = b.encode("utf-8")
    return base64.urlsafe_b64decode(b + b"=" * (-len(b) % 4))


def b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _digest(alg):
    return _DIGESTS[alg]


def _as_bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return str(value).encode("utf-8")


def _normalise_ring(ring):
    """Copy the keyring into a stable shape, preserving order and duplicates.

    Order is preserved but never relied on, and duplicate ``kid`` values are
    kept: a kid that was retired and later re-activated legitimately appears
    more than once, with disjoint windows.
    """
    if not ring:
        return None
    out = []
    for entry in ring:
        out.append({
            "kid": entry["kid"],
            "secret": _as_bytes(entry["secret"]),
            "activated": entry["activated"],
            "retired": entry.get("retired"),
        })
    return out


class JwtAlgNoneEngine:

    def __init__(self, config=None):
        config = config or {}
        self._key = _as_bytes(config.get("key", DEFAULT_KEY))
        self._keyring = _normalise_ring(config.get("keyring"))
        self._clock = config.get("clock") or time.time
        self._alg = DEFAULT_ALG

    # -- state -----------------------------------------------------------

    def _now(self):
        return int(self._clock())

    def reset(self):
        self._alg = DEFAULT_ALG

    def configure(self, options):
        if "key" in options:
            self._key = _as_bytes(options["key"])
        if "keyring" in options:
            self._keyring = _normalise_ring(options["keyring"])
        if "clock" in options:
            self._clock = options["clock"] or time.time
        if "alg" in options and options["alg"] in _DIGESTS:
            self._alg = options["alg"]

    # -- keyring ---------------------------------------------------------

    def _active_entry(self, now):
        """The entry to mint with: latest activation that has not retired."""
        best = None
        for entry in self._keyring:
            if entry["activated"] > now:
                continue
            if entry["retired"] is not None and entry["retired"] <= now:
                continue
            if best is None or entry["activated"] > best["activated"]:
                best = entry
        return best

    def _in_window(self, entry, iat):
        """Was this entry in force at iat, allowing for fleet clock skew?"""
        started = entry["activated"] - LEEWAY
        if iat < started:
            return False
        ends = entry["retired"]
        if ends is None:
            return True
        return iat < ends + LEEWAY

    def _lookup(self, kid, iat):
        matched = False
        for entry in self._keyring:
            if entry["kid"] != kid:
                continue
            matched = True
            if self._in_window(entry, iat):
                return entry
        if not matched:
            raise UnauthorizedError("unknown_kid", "no ring entry named %r" % (kid,))
        raise UnauthorizedError("key_window", "kid %r not in force at iat" % (kid,))

    # -- issue -----------------------------------------------------------

    def _sign(self, header, claims, secret=None):
        if secret is None:
            secret = self._key
        h = b64e(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        p = b64e(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        signing_input = ("%s.%s" % (h, p)).encode("utf-8")
        mac = hmac.new(secret, signing_input, _digest(header["alg"])).digest()
        return "%s.%s.%s" % (h, p, b64e(mac))

    def issue(self, payload, ttl=3600):
        now = self._now()
        header = {"alg": self._alg, "typ": "JWT"}
        if self._keyring is not None:
            entry = self._active_entry(now)
            if entry is None:
                raise UnauthorizedError("no_active_key", "no ring entry is in force")
            header["kid"] = entry["kid"]
            secret = entry["secret"]
        else:
            secret = self._key
        claims = {"iat": now, "exp": now + ttl}
        claims.update(payload)
        return self._sign(header, claims, secret)

    # -- verify ----------------------------------------------------------

    def verify(self, token):
        parts = token.split(".") if isinstance(token, str) else []
        if len(parts) != 3:
            raise ValidationError("malformed_parts", "token is not three segments")
        h, p, s = parts

        try:
            header = json.loads(b64d(h))
        except Exception:
            raise ValidationError("bad_header_b64", "header is not base64url JSON")
        if not isinstance(header, dict):
            raise ValidationError("header_not_object", "header is not a JSON object")

        try:
            claims = json.loads(b64d(p))
        except Exception:
            raise ValidationError("bad_payload_b64", "payload is not base64url JSON")
        if not isinstance(claims, dict):
            raise ValidationError("bad_payload_b64", "payload is not a JSON object")

        alg = header.get("alg")
        if isinstance(alg, str) and alg.strip().casefold() in _NEVER_ACCEPT:
            raise UnauthorizedError("alg_none", "unsigned algorithm is never accepted")
        if alg != self._alg:
            raise UnauthorizedError("alg_pin_mismatch", "header alg is not the pin")

        if self._keyring is not None:
            kid = header.get("kid")
            if not isinstance(kid, str):
                raise UnauthorizedError("unknown_kid", "header carries no kid")
            iat = claims.get("iat")
            if isinstance(iat, bool) or not isinstance(iat, (int, float)):
                raise UnauthorizedError("key_window", "token carries no usable iat")
            secret = self._lookup(kid, iat)["secret"]
        else:
            secret = self._key

        signing_input = ("%s.%s" % (h, p)).encode("utf-8")
        expected = hmac.new(secret, signing_input, _digest(self._alg)).digest()
        try:
            presented = b64d(s)
        except Exception:
            presented = b""
        if not hmac.compare_digest(presented, expected):
            raise UnauthorizedError("sig_mismatch", "signature does not match")

        now = self._now()
        exp = claims.get("exp")
        if isinstance(exp, (int, float)) and not isinstance(exp, bool) and exp < now:
            raise UnauthorizedError("expired", "token is past its exp")
        return claims

    # -- policy ----------------------------------------------------------

    def accept_unsigned(self, token):
        return False
