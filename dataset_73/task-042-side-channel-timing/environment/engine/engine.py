from __future__ import annotations
import hmac

class SideChannelEngine:

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def compare(self, a, b):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def is_constant_time(self, fn=None, size=4096, trials=9, iters=400):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
