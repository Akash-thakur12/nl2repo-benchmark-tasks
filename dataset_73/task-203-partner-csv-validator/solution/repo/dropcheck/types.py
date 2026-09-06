"""Column types and their parsing rules (spec sections 3.3, 4)."""
import re

INTEGER = re.compile(r"^-?[0-9]+$")                    # 4.2
DECIMAL = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")         # 4.3
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")     # 4.4

MONTH_LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


class Rejected(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _is_real_date(text):
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    if not 1 <= month <= 12:
        return False
    longest = 29 if month == 2 and _is_leap(year) else MONTH_LENGTHS[month - 1]
    return 1 <= day <= longest


def _integer(raw, _column, bounds):
    if not INTEGER.match(raw):                          # 4.2 nothing else allowed
        raise Rejected("TYPE")
    value = int(raw)
    # 3.3 the limits in force for this drop, resolved from the register by
    # limits.py. The min/max cached in the drop are deliberately ignored.
    low, high = bounds
    if (low is not None and value < low) or (high is not None and value > high):
        raise Rejected("RANGE")                         # both bounds inclusive
    return value


def _decimal(raw, _column, _bounds):
    if not DECIMAL.match(raw):
        raise Rejected("TYPE")
    return raw                                          # 4.3 original text


def _date(raw, _column, _bounds):
    if not DATE.match(raw) or not _is_real_date(raw):
        raise Rejected("TYPE")
    return raw


def _boolean(raw, _column, _bounds):
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise Rejected("TYPE")                              # 4.5 lower case only


PARSERS = {
    "string": lambda raw, _column, _bounds: raw,                 # 4.1 never trimmed
    "int": _integer,
    "decimal": _decimal,
    "date": _date,
    "bool": _boolean,
}


def parse(raw, column, bounds=(None, None)):
    """Parse one raw field. `bounds` is the (min, max) in force for the column,
    which the caller resolves from the register for the drop being validated."""
    if raw == "":
        if column["required"]:
            raise Rejected("REQUIRED")                  # 3.3
        return None                                     # 3.4 no range check
    parser = PARSERS.get(column["type"])
    if parser is None:
        raise ValueError("unknown column type {!r}".format(column["type"]))
    return parser(raw, column, bounds)
