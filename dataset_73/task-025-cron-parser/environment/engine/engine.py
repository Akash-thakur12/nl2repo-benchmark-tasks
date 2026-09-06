from __future__ import annotations
import datetime as dt

class CronParserEngine:
    FIELDS_5 = ['minute', 'hour', 'dom', 'month', 'dow']
    FIELDS_6 = ['second'] + FIELDS_5
    FIELDS_7 = FIELDS_6 + ['year']
    RANGES = {'minute': (0, 59), 'hour': (0, 23), 'dom': (1, 31), 'month': (1, 12), 'dow': (0, 7), 'second': (0, 59), 'year': (1970, 2099)}

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def parse(self, expr):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def _parse_field(self, val, lo, hi):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def next_after(self, expr, after_iso, horizon_days=1830):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
