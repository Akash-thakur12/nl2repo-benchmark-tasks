from __future__ import annotations


class IpRatingEngine:
    """Decode IEC 60529 IP markings and compare them against requirements.

    See instruction.md for the API contract, docs/ for the standard and the
    standards register, and samples/ for what the certification database and
    incoming inspection actually did.
    """

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def describe(self, code, tested_on=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def satisfies(self, mark, requirement):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def covers(self, mark, requirement):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
