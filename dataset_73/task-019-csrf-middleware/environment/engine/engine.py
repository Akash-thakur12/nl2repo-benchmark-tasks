from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class ValidationError(Exception):
    """A token is structurally missing or malformed."""


class UnauthorizedError(Exception):
    """Double-submit mismatch, bad signature, or a disallowed Origin/Referer."""


class CsrfMiddlewareEngine:
    """Double-submit-cookie CSRF middleware. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def issue(self, session_id):
        raise NotImplementedError(_STUB)

    def verify(self, headers, cookies, method, session_id=None):
        raise NotImplementedError(_STUB)
