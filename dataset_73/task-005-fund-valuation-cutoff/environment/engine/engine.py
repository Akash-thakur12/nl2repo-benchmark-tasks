from __future__ import annotations
import datetime as dt

# TODO(jrm, 2019-06): cutoff rolls back to the last pricing date on or before the
# requested date; weekend cutoffs use Friday's close. One price row per pricing
# date, last row loaded wins. See docs/ for the pack this was written from.

class StaleAuthorityError(Exception):
    pass

class FundNavEngine:

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def add_price(self, d, p, published_at=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def resolve_valuation_date(self, cutoff):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def nav(self, cutoff, units):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def nav_per_unit(self, cutoff):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def is_stale(self, cutoff):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
