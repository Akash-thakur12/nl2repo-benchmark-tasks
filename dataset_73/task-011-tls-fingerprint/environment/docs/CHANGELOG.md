# Fingerprint format changelog

## v2 — 2023-11

The v1 dissector (`legacy/dissector-v1.md`) was retired. Three changes, all of
which alter the emitted hash, so v1 and v2 records are not comparable:

- **Field 1 source corrected.** v1 read the version out of the record header.
  It is read from the handshake body now. On most modern clients these two
  differ, which is why the v1 hashes drifted away from the vendor-published
  ones.
- **Reserved (RFC 8701) values excluded.** v1 passed them through unmodified,
  so a Chrome fingerprint changed on almost every connection. v2 removes them
  from the 16-bit list fields. See `ja3-v2-field-notes.md`.
- **Extension order preserved.** v1 sorted the extension type list "so the dict
  keys are stable". Wire order is part of the client's identity and is kept.

Also in v2, the collector stores the raw record stream rather than the first
record's payload, because large ClientHellos were being truncated.

`legacy/dissector-v1.md` is kept on disk only so that pre-v2 hashes still in the
archive can be recomputed. Nothing produced today follows it.
