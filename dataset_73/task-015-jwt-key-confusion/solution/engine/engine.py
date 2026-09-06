from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json

from engine.verifier import detect_key_confusion  # re-exported for callers


class ValidationError(Exception):
    """Malformed token / unparseable or structurally invalid segment."""


class UnauthorizedError(Exception):
    """Algorithm mismatch (downgrade attempt) or failed signature check."""


#: The base64url alphabet (RFC 4648 section 5). Note the absence of '+', '/'
#: and '='. See environment/docs/segment-encoding.md.
_B64URL_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)

#: Algorithms whose latest in-force row in environment/data/alg_policy.csv is
#: `permitted` as of the snapshot date 2026-09-01. Transcribed from the
#: register; see environment/docs/alg-register.md.
#:   RS256  permitted 2021-01-01
#:   HS256  permitted 2022-07-15 (kept on purpose for the misconfiguration drill)
#:   PS256  proposed 2023-11-06, then permitted 2024-02-14
#:   RS384  permitted 2022-05-01; its `revoked` row is dated 2026-12-01, i.e.
#:          after the snapshot, so the withdrawal is not yet in force
#: Not pinnable: HS384 (revoked 2025-03-01), RS512 (revoked 2024-09-01),
#: ES512 (dated before the snapshot but only ever `proposed`), ES256
#: (`permitted`, but effective 2026-11-01, after the snapshot), and anything
#: with no row at all, such as "none".
PINNABLE_ALGS = frozenset({"RS256", "HS256", "PS256", "RS384"})


class _DuplicateMember(ValueError):
    """A JSON object repeated a member name."""


def _reject_duplicates(pairs):
    seen = set()
    for name, value in pairs:
        if name in seen:
            raise _DuplicateMember(name)
        seen.add(name)
    return dict(pairs)


def is_b64url(seg) -> bool:
    """True iff ``seg`` is a well-formed unpadded base64url segment."""
    if not isinstance(seg, str):
        return False
    if len(seg) % 4 == 1:
        return False
    return all(ch in _B64URL_ALPHABET for ch in seg)


def b64d(seg):
    """Strict unpadded-base64url decode.

    ``base64.urlsafe_b64decode`` alone is lax: it silently discards every
    character outside the alphabet, so '+', '/', '*', whitespace and stray
    padding all decode to something plausible. The alphabet is therefore
    checked *before* decoding rather than repaired.
    """
    if not is_b64url(seg):
        raise ValidationError("segment is not valid base64url")
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def b64e(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class JwtKeyConfusionEngine:
    """Mitigates RS256 -> HS256 key-confusion (CVE-2016-5431) by pinning the alg."""

    def __init__(self, config=None):
        cfg = config or {}
        self._hmac_key = cfg.get("hmac_key", b"hmac-secret")
        self._rsa_pub_pem = cfg.get(
            "rsa_pub",
            b"-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----\n",
        )
        self._expected = "RS256"

    def reset(self):
        self._expected = "RS256"

    def configure(self, options):
        """Request a pin change.

        The request is honoured only for algorithms in force as of the register
        snapshot; anything else leaves the pin unchanged and is not an error.
        """
        requested = (options or {}).get("alg")
        if requested in PINNABLE_ALGS:
            self._expected = requested

    def _decode_object(self, seg, what):
        try:
            obj = json.loads(b64d(seg), object_pairs_hook=_reject_duplicates)
        except _DuplicateMember as exc:
            raise ValidationError(
                "duplicate member %s in %s" % (exc.args[0], what)
            )
        except (ValueError, binascii.Error):
            raise ValidationError("unparseable %s" % what)
        if not isinstance(obj, dict):
            raise ValidationError("%s is not a JSON object" % what)
        return obj

    def verify(self, token):
        if not isinstance(token, str):
            raise ValidationError("token must be a string")
        parts = token.split(".")
        if len(parts) != 3:
            raise ValidationError("token must have three parts")
        h, p, s = parts

        # 1. Encoding: every segment, including the signature, before anything
        #    is decoded or any authorization decision is taken.
        for segment, what in ((h, "header"), (p, "payload"), (s, "signature")):
            if not is_b64url(segment):
                raise ValidationError("%s segment is not valid base64url" % what)

        # 2. Syntax and 3. duplicate members, for both JSON segments.
        header = self._decode_object(h, "header")
        payload = self._decode_object(p, "payload")

        # 4. Authorization. Exact, case-sensitive comparison.
        alg = header.get("alg")
        if alg != self._expected:
            raise UnauthorizedError(
                "algorithm %r rejected; server is pinned to %r" % (alg, self._expected)
            )

        # 5. Signature mechanism selected by the pin.
        if self._expected == "HS256":
            # Only reachable when the pin is (mis)configured to HS256: verify
            # the HMAC using the RSA public key bytes, i.e. detect the confused
            # key being used as a symmetric secret.
            expected_sig = hmac.new(
                self._rsa_pub_pem, ("%s.%s" % (h, p)).encode(), hashlib.sha256
            ).digest()
            if not hmac.compare_digest(b64d(s), expected_sig):
                raise UnauthorizedError("HMAC mismatch (key confusion?)")

        return payload

    @staticmethod
    def detects_confusion(header_alg, key_type):
        return detect_key_confusion(header_alg, key_type)
