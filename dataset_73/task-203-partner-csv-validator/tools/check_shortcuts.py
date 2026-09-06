#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out drop catches it.

Near-misses that the visible samples already catch do not belong here, because
they are not evidence that the held-out corpus does any work: the
newest-revision reading of docs/partner-limits.md is one of those, and it is
exercised in tools/check_crux.py instead.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_validator as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "drops"

BOM = "﻿"


# ----------------------------------------------------------- parser variants
def scan(body, escaped_quote=True, quote_anywhere=False, strip_bom=True,
         crlf=True):
    """One configurable RFC 4180 scanner, so each parser near-miss differs from
    the reference in exactly one way. Returns (start line, fields) pairs with
    physical line numbering, as the reference reader does."""
    if strip_bom and body.startswith(BOM):
        body = body[1:]
    records, field, row = [], [], []
    i, n = 0, len(body)
    quoted, started = False, False
    line = start_line = 1
    while i < n:
        ch = body[i]
        if quoted:
            if ch == '"':
                if escaped_quote and i + 1 < n and body[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                quoted = False
                i += 1
                continue
            if ch == "\n":
                line += 1
            field.append(ch)
            i += 1
            continue
        if ch == '"' and (quote_anywhere or (not field and not started)):
            quoted, started = True, True
            i += 1
            continue
        if ch == ",":
            row.append("".join(field))
            field, started = [], False
            i += 1
            continue
        if ch == "\n" or (crlf and ch == "\r" and i + 1 < n and body[i + 1] == "\n"):
            row.append("".join(field))
            records.append((start_line, row))
            field, row, started = [], [], False
            i += 2 if ch == "\r" else 1
            line += 1
            start_line = line
            continue
        field.append(ch)
        i += 1
    if field or row or started:
        row.append("".join(field))
        records.append((start_line, row))
    return records


def parse_naive_split(body):
    """No quoting at all: split on line terminators, then on commas."""
    text = body[1:] if body.startswith(BOM) else body
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [(number, line.split(",")) for number, line in enumerate(lines, start=1)]


def parse_no_escaped_quote(body):
    """Quoted fields, but "" inside a quoted field ends it."""
    return scan(body, escaped_quote=False)


def parse_quote_anywhere(body):
    """A double quote is special wherever it appears, not only at field start."""
    return scan(body, quote_anywhere=True)


def parse_no_bom_strip(body):
    """The byte-order mark is left on the first header name."""
    return scan(body, strip_bom=False)


def parse_lf_only(body):
    """Treats \\r as an ordinary character, so CRLF leaves it on the last field."""
    return scan(body, crlf=False)


# ------------------------------------------------------------ value variants
def value_required_is_type(raw, column, bounds):
    ok, reason, value = ref._parse_value(raw, column, bounds)
    if reason == "REQUIRED":
        return False, "TYPE", None
    return ok, reason, value


def value_optional_empty_is_blank(raw, column, bounds):
    if raw == "" and not column["required"]:
        return True, None, ""
    return ref._parse_value(raw, column, bounds)


def value_loose_int(raw, column, bounds):
    if column["type"] == "int" and raw != "":
        try:
            parsed = int(raw)                      # accepts "+1" and " 1"
        except ValueError:
            return False, "TYPE", None
        low, high = bounds
        if (low is not None and parsed < low) or (high is not None and parsed > high):
            return False, "RANGE", None
        return True, None, parsed
    return ref._parse_value(raw, column, bounds)


def value_float_int(raw, column, bounds):
    if column["type"] == "int" and raw != "":
        try:
            parsed = float(raw)                    # accepts "1.0" and "1e2"
        except ValueError:
            return False, "TYPE", None
        if parsed != int(parsed):
            return False, "TYPE", None
        parsed = int(parsed)
        low, high = bounds
        if (low is not None and parsed < low) or (high is not None and parsed > high):
            return False, "RANGE", None
        return True, None, parsed
    return ref._parse_value(raw, column, bounds)


def value_exclusive_range(raw, column, bounds):
    if column["type"] == "int" and raw != "" and ref.INT_RE.match(raw):
        parsed = int(raw)
        low, high = bounds
        if (low is not None and parsed <= low) or (high is not None and parsed >= high):
            return False, "RANGE", None
        return True, None, parsed
    return ref._parse_value(raw, column, bounds)


def value_decimal_as_float(raw, column, bounds):
    if column["type"] == "decimal" and raw != "":
        if not ref.DECIMAL_RE.match(raw):
            return False, "TYPE", None
        return True, None, str(float(raw))
    return ref._parse_value(raw, column, bounds)


def value_date_no_calendar(raw, column, bounds):
    if column["type"] == "date" and raw != "":
        if not ref.DATE_RE.match(raw):
            return False, "TYPE", None
        return True, None, raw                     # 2026-02-30 slips through
    return ref._parse_value(raw, column, bounds)


def value_bool_any_case(raw, column, bounds):
    if column["type"] == "bool" and raw != "":
        low = raw.lower()
        if low in ("true", "false"):
            return True, None, low == "true"
        return False, "TYPE", None
    return ref._parse_value(raw, column, bounds)


# ------------------------------------------------------------- limit lookups
def limits_as_of(drop, column):
    """The reference reading: the revision in force at captured_at."""
    return ref.limits_in_force(drop["partner"], column["name"], drop["captured_at"])


def limits_cached_in_drop(drop, column):
    """The min/max the capture agent cached in the drop's own schema block."""
    return column.get("min"), column.get("max")


def limits_latest_revision(drop, column):
    """The newest row in the register for this partner and column."""
    best = None
    for _rev, who, name, low, high, at in ref.LIMIT_REGISTER:
        if who == drop["partner"] and name == column["name"]:
            if best is None or at > best[0]:
                best = (at, low, high)
    return (None, None) if best is None else (best[1], best[2])


# ------------------------------------------------------------- the validator
def make_validate(parse=None, value=None, limits=None, header_ci=False,
                  by_position=False, missing_is_row_error=False,
                  allow_dup_header=False, pad_ragged=False, header_order=False,
                  dup_first=False, bad_row_reserves_key=False,
                  blank_is_data=False, blank_no_line=False, count_blanks=False,
                  line_mode="physical"):
    parse = parse or ref.parse_csv
    value = value or ref._parse_value
    limits = limits or limits_as_of

    def validate(drop):
        schema = drop["schema"]
        columns = schema["columns"]
        key = schema["key"]
        bounds = {c["name"]: limits(drop, c) for c in columns if c["type"] == "int"}
        records = parse(drop["csv"])
        rejected = {"status": "rejected", "accepted": [], "quarantined": [],
                    "extra_columns": [],
                    "totals": {"data_rows": 0, "accepted": 0, "quarantined": 0}}
        if not records:
            return dict(rejected, reject_reason="MISSING_COLUMNS")

        header = records[0][1]
        if not allow_dup_header and len(header) != len(set(header)):
            return dict(rejected, reject_reason="DUPLICATE_COLUMNS")

        if header_ci:
            lookup = {name.lower(): i for i, name in enumerate(header)}
            index_of = lambda c: lookup.get(c["name"].lower())  # noqa: E731
        elif by_position:
            index_of = lambda c: columns.index(c)               # noqa: E731
        else:
            lookup = {name: i for i, name in enumerate(header)}
            index_of = lambda c: lookup.get(c["name"])          # noqa: E731

        missing = [c for c in columns if index_of(c) is None]
        if missing and not missing_is_row_error:
            return dict(rejected, reject_reason="MISSING_COLUMNS")

        schema_names = {c["name"] for c in columns}
        extra = [n for n in header if n not in schema_names]

        order = sorted(columns, key=lambda c: index_of(c) if index_of(c) is not None else 1 << 30) \
            if header_order else columns

        accepted, quarantined, seen = [], [], set()
        data_rows = 0
        skipped_blank_lines = 0
        for ordinal, (physical, row) in enumerate(records[1:], start=2):
            if line_mode == "ordinal":
                line = ordinal
            elif line_mode == "end":
                line = physical + sum(f.count("\n") for f in row)
            else:
                line = physical - skipped_blank_lines
            blank = row == [""]
            if blank and not blank_is_data:
                if count_blanks:
                    data_rows += 1
                if blank_no_line:
                    skipped_blank_lines += 1   # a blank line takes no number
                continue
            data_rows += 1
            if len(row) != len(header):
                if pad_ragged:
                    row = (row + [""] * len(header))[:len(header)]
                else:
                    quarantined.append({"line": line, "reason": "RAGGED", "column": None})
                    continue
            if dup_first:
                idx = index_of(next(c for c in columns if c["name"] == key))
                raw_key = row[idx] if idx is not None and idx < len(row) else ""
                if raw_key in seen:
                    quarantined.append({"line": line, "reason": "DUPLICATE", "column": key})
                    continue
            parsed, failure = {}, None
            for column in order:
                idx = index_of(column)
                raw = row[idx] if idx is not None and idx < len(row) else ""
                ok, reason, val = value(raw, column, bounds.get(column["name"], (None, None)))
                if not ok:
                    failure = {"line": line, "reason": reason, "column": column["name"]}
                    break
                parsed[column["name"]] = val
            if failure is not None:
                if bad_row_reserves_key:
                    idx = index_of(next(c for c in columns if c["name"] == key))
                    if idx is not None and idx < len(row):
                        seen.add(row[idx])
                quarantined.append(failure)
                continue
            key_value = parsed.get(key)
            if not dup_first and key_value in seen:
                quarantined.append({"line": line, "reason": "DUPLICATE", "column": key})
                continue
            seen.add(key_value)
            accepted.append({c["name"]: parsed[c["name"]] for c in columns})

        return {"status": "ok", "reject_reason": None, "accepted": accepted,
                "quarantined": quarantined, "extra_columns": extra,
                "totals": {"data_rows": data_rows, "accepted": len(accepted),
                           "quarantined": len(quarantined)}}
    return validate


SHORTCUTS = [
    ("split on commas with no quoting at all", make_validate(parse=parse_naive_split)),
    ('a doubled quote inside a quoted field ends it', make_validate(parse=parse_no_escaped_quote)),
    ("a quote is special anywhere in a field", make_validate(parse=parse_quote_anywhere)),
    ("the byte-order mark is left on the first header name", make_validate(parse=parse_no_bom_strip)),
    ("a carriage return is an ordinary character", make_validate(parse=parse_lf_only)),
    ("interior blank lines count as data rows", make_validate(blank_is_data=True)),
    ("blank lines do not consume a line number", make_validate(blank_no_line=True)),
    ("blank lines are counted in data_rows", make_validate(count_blanks=True)),
    ("quarantine lines are the record's ordinal, not its line", make_validate(line_mode="ordinal")),
    ("quarantine lines name the line a record ends on", make_validate(line_mode="end")),
    ("header names are matched case-insensitively", make_validate(header_ci=True)),
    ("columns are matched by position, not by name", make_validate(by_position=True)),
    ("a missing column is a row error, not a rejected drop", make_validate(missing_is_row_error=True)),
    ("a duplicated header name is tolerated", make_validate(allow_dup_header=True)),
    ("ragged rows are padded to the header width", make_validate(pad_ragged=True)),
    ("columns are checked in header order", make_validate(header_order=True)),
    ("an empty required field is reported as TYPE", make_validate(value=value_required_is_type)),
    ("an empty optional field parses to the empty string", make_validate(value=value_optional_empty_is_blank)),
    ("ints are parsed with int(), so +1 and spaces pass", make_validate(value=value_loose_int)),
    ("ints are parsed through float, so 1.0 passes", make_validate(value=value_float_int)),
    ("range bounds are exclusive", make_validate(value=value_exclusive_range)),
    ("range limits come from the drop's cached min/max", make_validate(limits=limits_cached_in_drop)),
    ("decimals are parsed as floats", make_validate(value=value_decimal_as_float)),
    ("dates are shape-checked but not calendar-checked", make_validate(value=value_date_no_calendar)),
    ("booleans are matched case-insensitively", make_validate(value=value_bool_any_case)),
    ("duplicates are checked before the columns are", make_validate(dup_first=True)),
    ("a quarantined row still reserves its key", make_validate(bad_row_reserves_key=True)),
]


def main():
    sample_files = sorted(SAMPLES.glob("*.drop"))
    held_files = sorted(HELD_OUT.glob("*.drop"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.validate_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.validate_text(f.read_text(encoding="utf-8")) for f in held_files}

    def run(fn, path):
        return fn(json.loads(path.read_text(encoding="utf-8")))

    bad, uncaught, rows_out = [], [], []
    for label, fn in SHORTCUTS:
        ok = True
        for f in sample_files:
            try:
                if run(fn, f) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if run(fn, f) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows_out.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows_out)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows_out:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows_out))
    print("reproduce samples  : %d" % sum(1 for r in rows_out if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows_out if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out drop:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
