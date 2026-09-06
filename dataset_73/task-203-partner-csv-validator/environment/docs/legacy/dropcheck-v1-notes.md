# dropcheck v1 - implementation notes (RETIRED)

> **RETIRED.** These notes describe the v1 validator and the triage script
> carved out of it. They are kept for the archive of reports we sent partners
> before v2. Do not treat them as a specification.

## Reading a drop

Each drop is a JSON object with a `schema` and a `csv` body. v1 read the body
with a hand-written RFC 4180 reader: quoted fields, doubled quotes, CRLF, and a
byte-order mark on the first header name.

## Row numbering

Records are numbered as they come out of the reader. The header is record 1 and
the first data row is record 2, and a blank line is skipped but still takes its
number, so the numbers line up with the file for the ordinary drop where every
record is one line.

## Column checking

For each row, walk the header from left to right, and for every header column
that the schema knows about, check it. The first failure quarantines the row and
names that column; the rest of the row is not checked. This was chosen because
it matches the order a person reads the row in.

## Ranges

`min` and `max` are read from the drop's own schema block. The capture agent
puts the current limits there when it captures a drop, so the drop is
self-contained and triage needs nothing else on disk.

## Known divergences from v2

See `../CHANGELOG.md`: DROP-118 (line numbers), DROP-131 (column order) and
DROP-142 (where limits come from). Nothing in this file has been corrected for
any of them.
