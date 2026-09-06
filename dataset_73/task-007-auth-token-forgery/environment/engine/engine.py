from __future__ import annotations
import hmac, hashlib

FRAME_OCTETS = 8


class AuthTokenEngine:

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def add_sample(self, msg, token_hex, meta=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def sign(self, msg):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def verify(self, msg, token):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def tag_width_at(self, kid, ts):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def audit(self, record):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def audit_all(self, records):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def matching_keys(self, candidates):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def recover_key(self, candidates):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
