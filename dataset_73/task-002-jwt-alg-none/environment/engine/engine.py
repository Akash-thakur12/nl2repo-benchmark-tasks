from __future__ import annotations
import hmac, hashlib, base64, json, time


class ValidationError(Exception):
    """Structural damage. Carries the reason code as ``.code``."""
    code = None


class UnauthorizedError(Exception):
    """Policy / authentication failure. Carries the reason code as ``.code``."""
    code = None


def b64d(b):
    raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

def b64e(b):
    raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')


class JwtAlgNoneEngine:

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def _sign(self, header, claims, secret=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def issue(self, payload, ttl=3600):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    # alg pin is compared case-insensitively (see SEC-1142)
    def verify(self, token):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def accept_unsigned(self, token):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
