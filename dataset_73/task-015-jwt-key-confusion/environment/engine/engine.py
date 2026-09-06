from __future__ import annotations
import hmac, hashlib, base64, json

class ValidationError(Exception):
    pass

class UnauthorizedError(Exception):
    pass

def b64d(b):
    raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

def b64e(b):
    raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

class JwtKeyConfusionEngine:

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def verify(self, token):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
