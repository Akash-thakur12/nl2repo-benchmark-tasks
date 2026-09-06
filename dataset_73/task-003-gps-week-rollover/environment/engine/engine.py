from __future__ import annotations
import datetime as dt


class ValidationError(Exception):
    pass


class GpsRolloverEngine:

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def to_date(self, week, dow=0):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def from_date(self, d):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def resolve_week(self, raw, source="lnav", current_week=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def leap_offset(self, when, scale="utc"):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    # tow_count is seconds-of-week / 6 for this subframe (AN-0417 s2.1)
    def to_utc(self, raw_week, tow_count, source="lnav", current_week=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def from_utc(self, when):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
