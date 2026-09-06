"""Reference model for partner drop validation.

This follows docs/validation-spec.md, docs/drop-format.md and
docs/partner-limits.md as a whole: the specification states the rules, the
register states the limits in force, and the incident transcript in
docs/incidents/2026-05-12-partner-dispute.md pins the two rules the prose only
points at (physical line numbering, and the order columns are checked in).

This is the authority for expected output; nothing is hardcoded.
Section numbers in comments refer to validation-spec.md.
"""
import json
import re

INT_RE = re.compile(r"^-?[0-9]+$")                       # 4.2
DECIMAL_RE = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")        # 4.3
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")    # 4.4
DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# Transcribed from docs/partner-limits.md: (revision, partner, column, min,
# max, effective_at). A revision is in force from its effective instant
# INCLUSIVE until the next revision for the same partner and column.
LIMIT_REGISTER = [
    ("R1", "P-14", "qty", 1, 1000, "2025-01-01T00:00:00Z"),
    ("R2", "P-14", "qty", 1, 500, "2026-04-01T00:00:00Z"),
    ("R3", "P-22", "qty", 5, 250, "2025-06-01T00:00:00Z"),
]


def limits_in_force(partner, column_name, captured_at):
    """The (min, max) in force for this partner and column at the drop's capture
    instant, or (None, None) if no revision was in force yet. Instants use the
    fixed form YYYY-MM-DDTHH:MM:SSZ, so they order lexicographically."""
    best = None
    for _revision, who, column, low, high, effective_at in LIMIT_REGISTER:
        if who != partner or column != column_name:
            continue
        if effective_at > captured_at:                   # not yet in force
            continue
        if best is None or effective_at > best[0]:
            best = (effective_at, low, high)
    if best is None:
        return None, None
    return best[1], best[2]


def _leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _real_date(text):
    year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
    if not 1 <= month <= 12:
        return False
    limit = 29 if (month == 2 and _leap(year)) else DAYS[month - 1]
    return 1 <= day <= limit


def parse_csv(body):
    """RFC 4180 reader (section 1). Returns a list of (line, fields) pairs where
    `line` is the 1-based PHYSICAL line of the body on which the record begins.
    A quoted field may contain line breaks, so one record can span several
    physical lines. Blank lines are preserved as [""] so the caller can skip
    them while line numbering stays honest."""
    if body.startswith("﻿"):                        # 1.4
        body = body[1:]
    records, field, row = [], [], []
    i, n = 0, len(body)
    quoted = False
    started_quoted = False
    line = 1
    start_line = 1
    while i < n:
        ch = body[i]
        if quoted:
            if ch == '"':
                if i + 1 < n and body[i + 1] == '"':     # 1.2 escaped quote
                    field.append('"')
                    i += 2
                    continue
                quoted = False
                i += 1
                continue
            if ch == "\n":                               # a physical line ends
                line += 1
            field.append(ch)
            i += 1
            continue
        if ch == '"' and not field and not started_quoted:  # 1.3 only at start
            quoted = True
            started_quoted = True
            i += 1
            continue
        if ch == ",":
            row.append("".join(field))
            field, started_quoted = [], False
            i += 1
            continue
        if ch == "\n" or (ch == "\r" and i + 1 < n and body[i + 1] == "\n"):
            row.append("".join(field))                   # 1.1
            records.append((start_line, row))
            field, row, started_quoted = [], [], False
            i += 2 if ch == "\r" else 1
            line += 1
            start_line = line
            continue
        field.append(ch)
        i += 1
    if field or row or started_quoted:                   # 1.5 no phantom record
        row.append("".join(field))
        records.append((start_line, row))
    return records


def _parse_value(raw, column, bounds):
    """Return (ok, reason, value) for one field (sections 3.3, 4). `bounds` is
    the (min, max) in force for this column per docs/partner-limits.md."""
    kind = column["type"]
    if raw == "":
        if column["required"]:
            return False, "REQUIRED", None               # 3.3
        return True, None, None                          # 3.4
    if kind == "string":
        return True, None, raw                           # 4.1
    if kind == "int":
        if not INT_RE.match(raw):
            return False, "TYPE", None
        value = int(raw)
        low, high = bounds
        if (low is not None and value < low) or (high is not None and value > high):
            return False, "RANGE", None                  # 3.3 inclusive bounds
        return True, None, value
    if kind == "decimal":
        if not DECIMAL_RE.match(raw):
            return False, "TYPE", None
        return True, None, raw                           # 4.3 original string
    if kind == "date":
        if not DATE_RE.match(raw) or not _real_date(raw):
            return False, "TYPE", None
        return True, None, raw
    if kind == "bool":
        if raw == "true":
            return True, None, True
        if raw == "false":
            return True, None, False
        return False, "TYPE", None                       # 4.5
    raise ValueError("unknown column type %r" % (kind,))


def validate(drop):
    schema = drop["schema"]
    columns = schema["columns"]
    key = schema["key"]
    records = parse_csv(drop["csv"])

    # The limits that were in force for this partner at the instant the drop was
    # captured. The min/max cached in the drop's own schema block are only what
    # the capture agent held at the time and are not authoritative.
    bounds = {column["name"]: limits_in_force(drop["partner"], column["name"],
                                              drop["captured_at"])
              for column in columns if column["type"] == "int"}

    rejected = {"status": "rejected", "accepted": [], "quarantined": [],
                "extra_columns": [],
                "totals": {"data_rows": 0, "accepted": 0, "quarantined": 0}}

    if not records:
        return dict(rejected, reject_reason="MISSING_COLUMNS")

    header = records[0][1]
    if len(header) != len(set(header)):                  # 2.5
        return dict(rejected, reject_reason="DUPLICATE_COLUMNS")
    names = {name: index for index, name in enumerate(header)}
    if any(col["name"] not in names for col in columns):  # 2.3
        return dict(rejected, reject_reason="MISSING_COLUMNS")

    schema_names = {col["name"] for col in columns}
    extra = [name for name in header if name not in schema_names]   # 2.4

    accepted, quarantined = [], []
    seen_keys = set()
    data_rows = 0
    for line, row in records[1:]:
        if row == [""]:                                  # 1.6 blank line
            continue
        data_rows += 1
        if len(row) != len(header):                      # 3.1
            quarantined.append({"line": line, "reason": "RAGGED", "column": None})
            continue
        parsed, failure = {}, None
        for column in columns:                           # 3.2 schema order
            raw = row[names[column["name"]]]             # 2.2 by name
            ok, reason, value = _parse_value(
                raw, column, bounds.get(column["name"], (None, None)))
            if not ok:
                failure = {"line": line, "reason": reason, "column": column["name"]}
                break
            parsed[column["name"]] = value
        if failure is not None:
            quarantined.append(failure)
            continue
        key_value = parsed[key]
        if key_value in seen_keys:                       # 3.5 after all columns
            quarantined.append({"line": line, "reason": "DUPLICATE", "column": key})
            continue
        seen_keys.add(key_value)
        accepted.append(parsed)

    return {
        "status": "ok",
        "reject_reason": None,
        "accepted": accepted,
        "quarantined": quarantined,
        "extra_columns": extra,
        "totals": {"data_rows": data_rows,
                   "accepted": len(accepted),
                   "quarantined": len(quarantined)},
    }


def validate_text(text):
    return validate(json.loads(text))
