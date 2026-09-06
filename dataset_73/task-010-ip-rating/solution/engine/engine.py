"""IEC 60529 IP marking decoder and purchasing-spec comparator.

Two jobs:

  * ``describe`` turns a nameplate marking into a structured decode, read
    against the edition of IEC 60529 in force on the date of test;
  * ``satisfies`` (alias ``covers``) answers whether a part carrying a marking
    may be accepted against a purchasing requirement written as another
    marking.

Standard library only, and no runtime file reads: the register export shipped
in docs/iec60529-editions.json is embedded below verbatim so the engine works
wherever it is deployed.
"""
from __future__ import annotations

import datetime as _dt

# --------------------------------------------------------------------------
# Standards register (embedded copy of docs/iec60529-editions.json).
#
# An amendment entry carries only the table entries it changes and names the
# entry it extends; the export is in record order, not date order.
# --------------------------------------------------------------------------
EDITIONS = [
    {
        "id": "IEC 60529:1989+A1:1999",
        "effective": "1999-11-01",
        "extends": "IEC 60529:1989",
        "first_numeral": {},
        "second_numeral": {},
        "additional_letter": {},
        "supplementary_letter": {},
    },
    {
        "id": "IEC 60529:1989+A2:2013",
        "effective": "2013-08-01",
        "extends": "IEC 60529:1989+A1:1999",
        "first_numeral": {},
        "second_numeral": {"9": "high-pressure-jet"},
        "additional_letter": {},
        "supplementary_letter": {},
    },
    {
        "id": "IEC 60529:1989",
        "effective": "1989-11-15",
        "extends": None,
        "first_numeral": {
            "0": "none", "1": "solid-1", "2": "solid-2", "3": "solid-3",
            "4": "solid-4", "5": "dust-protected", "6": "dust-tight",
        },
        "second_numeral": {
            "0": "none", "1": "drip", "2": "drip-15", "3": "spray",
            "4": "splash", "5": "jet", "6": "powerful-jet",
            "7": "immersion-1m", "8": "submerged",
        },
        "additional_letter": {
            "A": "back-of-hand", "B": "finger", "C": "tool", "D": "wire",
        },
        "supplementary_letter": {
            "H": "high-voltage", "M": "motion-during-water-test",
            "S": "stationary-during-water-test", "W": "weather-conditions",
        },
    },
]

TABLE_KEYS = ("first_numeral", "second_numeral",
              "additional_letter", "supplementary_letter")

#: A characteristic position filled with the placeholder X: nothing stated.
UNSPECIFIED = "unspecified"
#: A characteristic that is stated but has no meaning in the governing edition.
UNKNOWN = "unknown"

#: Access protection implied by a first characteristic numeral on its own.
#: Passing the object test for a numeral necessarily excludes a probe of that
#: size, so the numeral alone already establishes an access degree.
ACCESS_FROM_NUMERAL = {
    0: "none", 1: "back-of-hand", 2: "finger", 3: "tool",
    4: "wire", 5: "wire", 6: "wire",
}
ACCESS_RANK = {"none": 0, "back-of-hand": 1, "finger": 2, "tool": 3, "wire": 4}
ADDITIONAL_RANK = {"A": 1, "B": 2, "C": 3, "D": 4}
SUPPLEMENTARY_LETTERS = ("H", "M", "S", "W")

#: Object protection is one cumulative ladder: n meets every requirement at or
#: below n.
SOLID_COVERS = {n: frozenset(range(n + 1)) for n in range(7)}

#: Liquid protection is cumulative only through the jet tests. Immersion (7, 8)
#: and the high-pressure apparatus (9) are separate test methods and do not
#: imply the jet tests, though each still covers the 0-4 series.
LIQUID_COVERS = {
    0: frozenset({0}),
    1: frozenset({0, 1}),
    2: frozenset({0, 1, 2}),
    3: frozenset({0, 1, 2, 3}),
    4: frozenset({0, 1, 2, 3, 4}),
    5: frozenset({0, 1, 2, 3, 4, 5}),
    6: frozenset({0, 1, 2, 3, 4, 5, 6}),
    7: frozenset({0, 1, 2, 3, 4, 7}),
    8: frozenset({0, 1, 2, 3, 4, 7, 8}),
    9: frozenset({0, 1, 2, 3, 4, 9}),
}


# --------------------------------------------------------------------------
# Register lookup
# --------------------------------------------------------------------------
def _as_date(value):
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        try:
            return _dt.date.fromisoformat(value.strip())
        except ValueError:
            raise ValueError("not an ISO date: %r" % value)
    raise ValueError("test date must be a date or an ISO date string, got %s"
                     % type(value).__name__)


def resolve_edition(tested_on=None):
    """Return (edition_id, tables) for the edition in force on a date.

    The governing entry is the one with the latest effective date that is not
    after the date of test; with no date, the newest entry governs. Its tables
    are the merge of every entry along the extends chain, base first.
    """
    day = _as_date(tested_on)
    by_id = {entry["id"]: entry for entry in EDITIONS}
    ordered = sorted(EDITIONS, key=lambda entry: _as_date(entry["effective"]))
    if day is None:
        governing = ordered[-1]
    else:
        in_force = [e for e in ordered if _as_date(e["effective"]) <= day]
        if not in_force:
            raise ValueError("no edition of IEC 60529 was in force on %s"
                             % day.isoformat())
        governing = in_force[-1]

    chain = []
    node = governing
    seen = set()
    while node is not None and node["id"] not in seen:
        seen.add(node["id"])
        chain.append(node)
        node = by_id.get(node.get("extends")) if node.get("extends") else None

    tables = {key: {} for key in TABLE_KEYS}
    for node in reversed(chain):
        for key in TABLE_KEYS:
            tables[key].update(node.get(key) or {})
    return governing["id"], tables


# --------------------------------------------------------------------------
# Marking grammar (clause 4.1)
# --------------------------------------------------------------------------
def _strip_separators(text):
    return "".join(ch for ch in text if not ch.isspace() and ch != "-")


def _characteristic(char, whole):
    if char == "X":
        return None
    if char.isdigit():
        return int(char)
    raise ValueError("character not a numeral or X: %r" % whole)


def _canonical(first, second, additional, supplementary):
    out = "IP"
    out += "X" if first is None else str(first)
    out += "X" if second is None else str(second)
    if additional:
        out += additional
    if supplementary:
        out += supplementary
    return out


def _parse_code(part, whole):
    body = part[2:] if part.startswith("IP") else part
    if len(body) < 2:
        raise ValueError("fewer than two characteristic positions: %r" % whole)
    first = _characteristic(body[0], whole)
    second = _characteristic(body[1], whole)

    additional = None
    supplementary = None
    for char in body[2:]:
        if char in ADDITIONAL_RANK:
            if supplementary is not None:
                raise ValueError(
                    "supplementary letter precedes additional letter: %r"
                    % whole)
            if additional is not None:
                raise ValueError("two additional letters: %r" % whole)
            additional = char
        elif char in SUPPLEMENTARY_LETTERS:
            if supplementary is not None:
                raise ValueError("two supplementary letters: %r" % whole)
            supplementary = char
        elif char.isdigit():
            raise ValueError("third numeral: %r" % whole)
        else:
            raise ValueError(
                "letter is neither an additional nor a supplementary letter: "
                "%r" % whole)

    if additional is not None and first is not None:
        implied = ACCESS_RANK.get(ACCESS_FROM_NUMERAL.get(first, ""), 0)
        if ADDITIONAL_RANK[additional] < implied:
            raise ValueError(
                "additional letter lower than protection implied by first "
                "numeral: %r" % whole)

    return {
        "first": first,
        "second": second,
        "additional": additional,
        "supplementary": supplementary,
        "text": _canonical(first, second, additional, supplementary),
    }


def parse_mark(mark):
    """Split a marking into its codes and parse each one."""
    if not isinstance(mark, str):
        raise ValueError("marking must be a string, got %s"
                         % type(mark).__name__)
    cleaned = _strip_separators(mark).upper()
    if not cleaned:
        raise ValueError("empty marking")
    parts = cleaned.split("/")
    if any(not part for part in parts):
        raise ValueError("empty code in a dual marking: %r" % mark)
    return [_parse_code(part, mark) for part in parts]


def _code_access(code, tables):
    """Access value one code establishes, as a word."""
    if code["additional"] is not None:
        return tables["additional_letter"].get(code["additional"], UNKNOWN)
    if code["first"] is None:
        return UNSPECIFIED
    if str(code["first"]) not in tables["first_numeral"]:
        return UNKNOWN
    return ACCESS_FROM_NUMERAL.get(code["first"], UNKNOWN)


def _access_rank(code):
    """Access ladder position one code establishes (0 = nothing)."""
    if code["additional"] is not None:
        return ADDITIONAL_RANK[code["additional"]]
    if code["first"] is None:
        return 0
    return ACCESS_RANK.get(ACCESS_FROM_NUMERAL.get(code["first"], ""), 0)


class IpRatingEngine:
    """Decode IEC 60529 markings and compare them against requirements."""

    def __init__(self, config=None):
        self._config = dict(config or {})

    def reset(self):
        """No-op: the decoder is stateless."""

    def configure(self, options):
        """No-op: the decoder is stateless."""

    # ------------------------------------------------------------------
    def describe(self, code, tested_on=None):
        """Decode a nameplate marking as of the date it was tested."""
        codes = parse_mark(code)
        edition_id, tables = resolve_edition(tested_on)

        firsts = [c["first"] for c in codes if c["first"] is not None]
        seconds = [c["second"] for c in codes if c["second"] is not None]

        solid = (tables["first_numeral"].get(str(max(firsts)), UNKNOWN)
                 if firsts else UNSPECIFIED)
        liquid = (tables["second_numeral"].get(str(max(seconds)), UNKNOWN)
                  if seconds else UNSPECIFIED)

        best = None
        saw_unknown = False
        for one in codes:
            value = _code_access(one, tables)
            if value in ACCESS_RANK:
                if best is None or ACCESS_RANK[value] > ACCESS_RANK[best]:
                    best = value
            elif value == UNKNOWN:
                saw_unknown = True
        if best is not None:
            access = best
        elif saw_unknown:
            access = UNKNOWN
        else:
            access = UNSPECIFIED

        supplementary = None
        for one in codes:
            if one["supplementary"] is not None:
                supplementary = tables["supplementary_letter"].get(
                    one["supplementary"], UNKNOWN)
                break

        return {
            "solid": solid,
            "liquid": liquid,
            "dust_tight": any(value == 6 for value in firsts),
            "access": access,
            "supplementary": supplementary,
            "codes": [one["text"] for one in codes],
            "edition": edition_id,
        }

    # ------------------------------------------------------------------
    def satisfies(self, mark, requirement):
        """True when a part marked `mark` may be accepted against `requirement`.

        The object numeral, the liquid numeral and access protection are three
        independent dimensions, and all three must be met. A marking with more
        than one code establishes the union of what its codes establish in each
        dimension, so a dual mark can meet a requirement no single code of it
        meets on its own.
        """
        have = parse_mark(mark)
        want = parse_mark(requirement)

        solid_covered = set()
        liquid_covered = set()
        access_covered = set()
        for one in have:
            if one["first"] is not None:
                solid_covered |= set(
                    SOLID_COVERS.get(one["first"], frozenset({one["first"]})))
            if one["second"] is not None:
                liquid_covered |= set(
                    LIQUID_COVERS.get(one["second"],
                                      frozenset({one["second"]})))
            access_covered |= set(range(1, _access_rank(one) + 1))

        needed_solid = max(
            [one["first"] for one in want if one["first"] is not None],
            default=None)
        needed_liquid = max(
            [one["second"] for one in want if one["second"] is not None],
            default=None)
        needed_access = max(
            [ADDITIONAL_RANK[one["additional"]] for one in want
             if one["additional"] is not None],
            default=None)

        if needed_solid is not None and needed_solid not in solid_covered:
            return False
        if needed_liquid is not None and needed_liquid not in liquid_covered:
            return False
        if needed_access is not None and needed_access not in access_covered:
            return False
        return True

    def covers(self, mark, requirement):
        """Alias of satisfies."""
        return self.satisfies(mark, requirement)
