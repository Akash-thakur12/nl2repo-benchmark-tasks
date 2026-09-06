"""MiFID II RTS 22 transaction-report field validator.

`validate` returns a list of error strings (empty == valid). It checks required
fields, enumerations, an ISO-8601 timestamp, positive price / quantity, an ISO
17442 LEI (mod-97), an ISO 6166 ISIN (Luhn check digit) and an ISO 10383 MIC.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from engine.schema import CAPACITIES, KNOWN_MICS, MANDATORY_FIELDS, SIDES


def _lei_valid(lei):
    if not isinstance(lei, str) or len(lei) != 20 or not lei.isalnum() or lei != lei.upper():
        return False
    try:
        digits = "".join(str(int(ch, 36)) for ch in lei)
    except ValueError:
        return False
    return int(digits) % 97 == 1


def _isin_valid(isin):
    if not isinstance(isin, str) or len(isin) != 12:
        return False
    if not (isin[:2].isalpha() and isin[:11].isalnum() and isin[-1].isdigit()):
        return False
    body = "".join(str(int(ch, 36)) for ch in isin[:11])
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10 == int(isin[-1])


class MifidEngine:
    REQUIRED = MANDATORY_FIELDS
    SIDES = SIDES
    CAPS = CAPACITIES

    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def validate(self, record):
        errors = []
        for key in self.REQUIRED:
            if key not in record:
                errors.append(f"missing:{key}")
        if errors:
            return errors

        if record["SIDE"] not in self.SIDES:
            errors.append("bad:SIDE")
        if record["CAPACITY"] not in self.CAPS:
            errors.append("bad:CAPACITY")
        try:
            dt.datetime.fromisoformat(record["TS"])
        except (ValueError, TypeError):
            errors.append("bad:TS")
        price = record["PRICE"]
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
            errors.append("bad:PRICE")
        qty = record["QTY"]
        if not isinstance(qty, (int, float)) or isinstance(qty, bool) or qty <= 0:
            errors.append("bad:QTY")
        if not _lei_valid(record["LEI"]):
            errors.append("bad:LEI")
        if not _isin_valid(record["ISIN"]):
            errors.append("bad:ISIN")
        if record["VENUE"] not in KNOWN_MICS:
            errors.append("bad:VENUE")
        return errors

    def hash_report(self, record):
        canonical = repr(sorted((str(k), str(v)) for k, v in record.items()))
        return hashlib.sha256(canonical.encode()).hexdigest()
