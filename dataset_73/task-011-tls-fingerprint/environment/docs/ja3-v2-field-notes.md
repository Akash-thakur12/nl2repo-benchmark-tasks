# JA3 v2 field notes

Status: **current**. This is the live specification of the fingerprint fields
produced by the dissector. It replaces `legacy/dissector-v1.md` (see
`CHANGELOG.md` for what changed and when).

## Input format

A capture is the raw record stream for the client's first flight, stored as
hex. It is what came off the wire, not a pre-parsed message: a single handshake
message may span more than one record, and consecutive records of the same
content type carry no framing of their own beyond the 5-byte header. Every
capture in `../corpus/` was collected this way.

## The five fields

The fingerprint is five fields joined with `,` in this order:

1. **version** — the version the client advertises inside the handshake body.
   The record header version is a transport artefact of the record layer and is
   never used: modern stacks pin it to a low value for middlebox compatibility,
   and when a message is split across records there is no single record header
   to point at anyway.
2. **cipher suites** — the offered suites, in the order they appear on the wire.
3. **extension types** — the extension type numbers, in the order they appear on
   the wire.
4. **supported groups** ("elliptic curves") — the group ids from the `0x000A`
   extension, in wire order.
5. **EC point formats** — the format bytes from the `0x000B` extension, in wire
   order.

Fields 2-5 are the relevant integers joined with `-`. A field whose list is
empty is written as the single character `0`.

`ja3_hash` is the MD5 of the joined string, lowercase hex.

## Reserved values excluded from the fingerprint

RFC 8701 reserves sixteen 16-bit values as placeholders. A client sprinkles
them into its offers so that servers and middleboxes stay tolerant of unknown
values; they mean nothing, they vary from connection to connection, and a
fingerprint that included them would not be stable. They are removed from every
**16-bit** list field before the field is joined. Note the width: the reserved
set is defined only for 16-bit values, so an 8-bit list can never contain one
and is never filtered.

| | | | |
|---|---|---|---|
| 0x0A0A | 0x1A1A | 0x2A2A | 0x3A3A |
| 0x4A4A | 0x5A5A | 0x6A6A | 0x7A7A |
| 0x8A8A | 0x9A9A | 0xAAAA | 0xBABA |
| 0xCACA | 0xDADA | 0xEAEA | 0xFAFA |

The list is closed — it is exactly these sixteen values and nothing else. In
particular, do **not** approximate it with a test on the low byte or on a
nibble: extension type `0x000A` (supported groups) and `0x000B` (EC point
formats) both look like reserved values to such a test, and dropping `0x000A`
quietly empties field 4 as well as shortening field 3.

## Ground truth

`../corpus/expected.csv` holds one row per capture with each of the five fields
in its own column plus the joined `ja3` string and `ja3_hash`. It is produced by
the production collector and is authoritative. Replaying the corpus and diffing
column by column is the supported way to check a dissector.
