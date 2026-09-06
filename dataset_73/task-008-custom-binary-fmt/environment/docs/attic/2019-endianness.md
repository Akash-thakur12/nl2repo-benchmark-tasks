# BIN1 byte order and table notes (2019-05)

> **SUPERSEDED by `docs/wire-format.md` (2021-03). Retained for archaeology.**
> Nothing in this file has been re-checked against a current blob.

Notes from the 2019 interop debugging round, when the Solaris collectors were
still in the fleet.

## Byte order of `name_len`

The early writers (anything before the 2020 rewrite) emitted `name_len`
**big-endian** while the rest of the header was little-endian. This is the usual
cause of a reader reporting an absurd name length such as 65535 on a blob that
is obviously only a few dozen bytes long: byte-swap the field and the length
becomes sane again. `tools/bin1check.py` was extended to say so in its error
text.

## The tag table

The tag table is flat: one row per tag, and the encoding for a tag is a property
of the tag, not of when the blob was written. Reading historical captures with
today's table is therefore safe.

## Name table lifetime

The name table is shared across a collector *session*, not reset per blob, so
the second blob in a session can refer back to a name that only appeared in the
first one. Tools that process a single blob in isolation cannot resolve those
references and should skip them.
