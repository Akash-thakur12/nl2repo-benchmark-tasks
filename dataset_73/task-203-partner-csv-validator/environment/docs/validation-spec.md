# Partner drop validation specification

This document specifies how we validate a partner's CSV drop against the schema
they were issued. The tool must reproduce it exactly.

## 1. Parsing

The CSV body follows RFC 4180.

**1.1** Fields are separated by commas and records by line breaks. Both `\n` and
`\r\n` terminate a record; a `\r` immediately before a record-terminating `\n`
is part of the terminator and never part of a field.

**1.2** A field may be wrapped in double quotes. Inside a quoted field a comma,
a `\r`, and a `\n` are ordinary characters, and two consecutive double quotes
are one literal double quote.

**1.3** Quotes are only special at the very start of a field. `ab"cd` is the
five-character value `ab"cd`.

**1.4** A byte-order mark at the very start of the body is stripped before
anything else.

**1.5** If the body ends with a record terminator, that terminator does not
create an additional empty record.

**1.6** A record consisting of a single empty field is a blank line. Blank lines
anywhere in the body are skipped and are not counted as data rows.

## 2. Header

**2.1** The first record is the header. Column names are compared **exactly**:
case, spacing and punctuation all matter.

**2.2** Header columns may appear in any order. Values are matched to schema
columns by name, never by position.

**2.3** If any schema column is absent from the header the whole drop is
rejected: `status` is `"rejected"`, `reject_reason` is `"MISSING_COLUMNS"`, and
`accepted`, `quarantined` and `extra_columns` are all empty. No rows are
examined.

**2.4** Header columns not named in the schema are recorded in `extra_columns`
in the order they appear in the header, and their values are ignored.

**2.5** A duplicated header name rejects the drop with reason
`"DUPLICATE_COLUMNS"`, under the same rules as 2.3.

## 3. Rows

Data rows are the records after the header, in file order. `line` in a
quarantine entry identifies the record so that the partner can find it in the
file they sent us without recounting anything. The header is line 1.

**3.1** A row whose field count differs from the header's is quarantined with
reason `"RAGGED"` and no `column`. It is never padded or truncated.

**3.2** Otherwise the row's schema columns are checked in a fixed order. The
first failure quarantines the row, and the remaining columns are not checked.
The quarantine entry names the `column` that failed.

**3.3** Checks per column, in this order:

- `REQUIRED` - the column is required and its raw value is the empty string.
- `TYPE` - the value does not parse as the column's type.
- `RANGE` - the parsed value is outside the limits in force for that column
  (see `docs/partner-limits.md`). Both bounds are inclusive.

**3.4** A column that is not required and whose raw value is the empty string
parses to `null` and is not range-checked.

**3.5** Only after every column passes is the row checked for duplication. If
the drop's key column has already been accepted with this value, the row is
quarantined with reason `"DUPLICATE"` and `column` set to the key column. The
first row with a given key is accepted; later ones are quarantined.

## 4. Types

**4.1** `string` - accepted as-is. Never trimmed.

**4.2** `int` - an optional `-` followed by one or more digits, nothing else. A
leading `+`, surrounding whitespace, a decimal point, an exponent, underscores,
or a value such as `1.0` are all `TYPE` failures. The parsed value is a JSON
number, and is then range-checked per 3.3.

**4.3** `decimal` - an optional `-`, then digits, then optionally `.` followed
by one or more digits. No exponent, no leading `+`, no whitespace. The parsed
value is reported as the **original string**, unchanged, so no precision is
lost.

**4.4** `date` - exactly `YYYY-MM-DD`, ten characters, all digits except the two
hyphens, and a real calendar date. `2026-1-5`, `2026-02-30` and `20260105` are
all `TYPE` failures. The parsed value is the original string.

**4.5** `bool` - exactly `true` or `false`, lower case. `TRUE`, `1` and `yes`
are `TYPE` failures. The parsed value is a JSON boolean.

## 5. Report

**5.1** `accepted` holds one object per accepted row, with one member per schema
column, in schema order, carrying the parsed value. Extra columns never appear.

**5.2** `quarantined` holds one entry per quarantined row, in row order, each
with `line`, `reason` and `column` (`null` for `RAGGED`).

**5.3** `totals.data_rows` counts records after the header, excluding blank
lines. `totals.accepted` and `totals.quarantined` must sum to it.

## 6. Where the rules live

The prose above is normative but not self-contained. `docs/drop-format.md`
defines the capture format and the report schema, `docs/partner-limits.md` is
the register of range limits, and `docs/incidents/` holds worked examples of
drops we have had to defend to a partner, each with the exact report we
returned. `docs/CHANGELOG.md` records what changed between v1 and v2 of the
validator and which artefacts have not caught up.
