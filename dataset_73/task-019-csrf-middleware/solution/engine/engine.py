from __future__ import annotations

import hashlib
import hmac

from engine.tokens import generate_csrf_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class ValidationError(Exception):
    """A token is structurally missing or malformed."""


class UnauthorizedError(Exception):
    """Double-submit mismatch, bad signature, or a disallowed Origin/Referer."""


def _origin_host(url):
    # crude scheme://host[:port]/... -> "scheme://host[:port]"
    if "://" not in url:
        return url.rstrip("/")
    scheme, rest = url.split("://", 1)
    host = rest.split("/", 1)[0]
    return f"{scheme}://{host}"


class CsrfMiddlewareEngine:
    """Double-submit-cookie CSRF middleware with Origin/Referer enforcement."""

    def __init__(self, config=None):
        cfg = config or {}
        secret = cfg.get("secret", b"csrf-secret")
        self._secret = secret if isinstance(secret, bytes) else secret.encode()
        self._allowed = set(cfg.get("allowed_origins", []))

    def reset(self):
        pass

    def configure(self, options):
        if "secret" in options:
            s = options["secret"]
            self._secret = s if isinstance(s, bytes) else s.encode()
        if "allowed_origins" in options:
            self._allowed = set(options["allowed_origins"])

    def _sign(self, session_id, nonce):
        return hmac.new(
            self._secret, f"{session_id}:{nonce}".encode(), hashlib.sha256
        ).hexdigest()

    def issue(self, session_id):
        nonce = generate_csrf_token()
        return f"{nonce}.{self._sign(session_id, nonce)}"

    @staticmethod
    def _header(headers, name):
        low = name.lower()
        for k, v in headers.items():
            if k.lower() == low:
                return v
        return None

    def verify(self, headers, cookies, method, session_id=None):
        if method.upper() in SAFE_METHODS:
            return True

        header_token = self._header(headers, "X-CSRF-Token")
        cookie_token = cookies.get("csrf_token")
        if not header_token or not cookie_token:
            raise ValidationError("missing CSRF token (header and/or cookie)")

        # double-submit: header and cookie tokens must be identical
        if not hmac.compare_digest(header_token, cookie_token):
            raise UnauthorizedError("double-submit token mismatch")

        try:
            nonce, sig = header_token.split(".")
        except ValueError:
            raise ValidationError("malformed CSRF token")
        if session_id is not None:
            if not hmac.compare_digest(sig, self._sign(session_id, nonce)):
                raise UnauthorizedError("bad CSRF signature")

        origin = self._header(headers, "Origin")
        referer = self._header(headers, "Referer")
        source = origin or referer
        if source is not None and self._allowed:
            if _origin_host(source) not in self._allowed:
                raise UnauthorizedError(f"origin {source!r} not allowed")
        return True
