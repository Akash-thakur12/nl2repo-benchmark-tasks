#!/usr/bin/env python3
"""triage.py - explain one drop, row by row (dropcheck v1).

The support desk runs this when a partner asks why a row of theirs was
quarantined: it prints every data row with the verdict and, for a quarantined
row, the reason and the column that failed.

    python3 triage.py <drop file> [row number]

How it decides, so the desk can quote it back:

  * Rows are numbered as they come out of the CSV reader. The header is 1 and
    the first data row is 2; a blank line is skipped but keeps its number.
  * Columns are checked left to right as they appear in the partner's header.
    The first column that fails quarantines the row and is the column we name.
  * Integer ranges come from the "min" and "max" the capture agent wrote into
    the drop's own schema block, so triage needs nothing else on disk.

Retired with dropcheck v1 - see ../docs/legacy/dropcheck-v1-notes.md and the
divergences listed in ../docs/CHANGELOG.md. Still installed because the desk
uses it daily.
"""
import json
import re
import sys

INT_RE = re.compile(r"^-?[0-9]+$")
DECIMAL_RE = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def read_csv(body):
    """RFC 4180: quoted fields, doubled quotes, CRLF, byte-order mark. Blank
    lines come back as [""] so they can be skipped by the caller."""
    if body.startswith("﻿"):
        body = body[1:]
    records, field, row = [], [], []
    i, n = 0, len(body)
    quoted = started = False
    while i < n:
        ch = body[i]
        if quoted:
            if ch == '"':
                if i + 1 < n and body[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                quoted = False
                i += 1
                continue
            field.append(ch)
            i += 1
            continue
        if ch == '"' and not field and not started:
            quoted = started = True
            i += 1
            continue
        if ch == ",":
            row.append("".join(field))
            field, started = [], False
            i += 1
            continue
        if ch == "\n" or (ch == "\r" and i + 1 < n and body[i + 1] == "\n"):
            row.append("".join(field))
            records.append(row)
            field, row, started = [], [], False
            i += 2 if ch == "\r" else 1
            continue
        field.append(ch)
        i += 1
    if field or row or started:
        row.append("".join(field))
        records.append(row)
    return records


def real_date(text):
    year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
    if not 1 <= month <= 12:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 1 <= day <= (29 if month == 2 and leap else DAYS[month - 1])


def check(raw, column):
    """Return (reason, value): reason is None when the field is fine."""
    if raw == "":
        return ("REQUIRED", None) if column["required"] else (None, None)
    kind = column["type"]
    if kind == "string":
        return None, raw
    if kind == "int":
        if not INT_RE.match(raw):
            return "TYPE", None
        value = int(raw)
        low, high = column.get("min"), column.get("max")
        if (low is not None and value < low) or (high is not None and value > high):
            return "RANGE", None
        return None, value
    if kind == "decimal":
        return (None, raw) if DECIMAL_RE.match(raw) else ("TYPE", None)
    if kind == "date":
        if DATE_RE.match(raw) and real_date(raw):
            return None, raw
        return "TYPE", None
    if kind == "bool":
        if raw in ("true", "false"):
            return None, raw == "true"
        return "TYPE", None
    return "TYPE", None


def triage(drop, wanted=None):
    schema = drop["schema"]
    columns = {c["name"]: c for c in schema["columns"]}
    records = read_csv(drop["csv"])
    if not records:
        print("empty drop")
        return
    header = records[0]
    missing = [c["name"] for c in schema["columns"] if c["name"] not in header]
    if missing:
        print("drop rejected: MISSING_COLUMNS (%s)" % ", ".join(missing))
        return
    if len(header) != len(set(header)):
        print("drop rejected: DUPLICATE_COLUMNS")
        return

    print("drop from %s captured %s" % (drop.get("partner", "?"),
                                        drop.get("captured_at", "?")))
    seen = set()
    number = 1
    for record in records[1:]:
        number += 1
        if record == [""]:
            continue
        if wanted is not None and number != wanted:
            continue
        if len(record) != len(header):
            print("row %d: QUARANTINED RAGGED (%d fields, header has %d)"
                  % (number, len(record), len(header)))
            continue
        verdict = None
        for position, name in enumerate(header):       # the partner's order
            column = columns.get(name)
            if column is None:
                continue                               # not ours; ignored
            reason, _value = check(record[position], column)
            if reason is not None:
                verdict = (reason, name, record[position])
                break
        if verdict is not None:
            print("row %d: QUARANTINED %s in column %r (value %r)"
                  % (number, verdict[0], verdict[1], verdict[2]))
            continue
        key = record[header.index(schema["key"])]
        if key in seen:
            print("row %d: QUARANTINED DUPLICATE key %r" % (number, key))
            continue
        seen.add(key)
        print("row %d: accepted (key %r)" % (number, key))


def main(argv):
    if not 2 <= len(argv) <= 3:
        sys.stderr.write("usage: triage.py <drop file> [row number]\n")
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        drop = json.load(handle)
    triage(drop, int(argv[2]) if len(argv) == 3 else None)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
