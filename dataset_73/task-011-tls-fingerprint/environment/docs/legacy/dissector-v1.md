# ClientHello dissector — v1 field specification

> **SUPERSEDED 2023-11 — retained for hash-archaeology on pre-v2 fingerprint
> records.** Do not implement from this document. The live specification is
> `../ja3-v2-field-notes.md`; `../CHANGELOG.md` lists what v2 changed.

## Record / ClientHello layout

```
record:    type(1)=0x16 | version(2) | length(2) | handshake bytes
handshake: msg_type(1)=0x01 | length(3) | client_version(2) | random(32)
           | session_id_len(1) | session_id(...)
           | cipher_suites_len(2) | cipher_suites(2 bytes each)
           | compression_methods_len(1) | compression_methods(...)
           | [ extensions_len(2) | { ext_type(2) ext_len(2) ext_data } * ]
```

Two extensions are decoded further:

- `0x000A` supported groups / "elliptic curves": `list_len(2)` then `u16` ids.
- `0x000B` EC point formats: `count(1)` then that many `u8` formats.

## Fingerprint string

```
ja3 = "{record_version},{ciphers},{ext_types},{curves},{point_formats}"
```

- `record_version` is the version field of the record header — the first 16-bit
  field in the buffer, at offset 1.
- `ext_types` is sorted ascending so the dict keys are stable.
- Each of the last four fields is the relevant integers joined by `-`, or the
  literal `"0"` when the list is empty.
- Reserved / GREASE values are passed through unmodified.

`ja3_hash` is `md5(ja3)` as a lowercase hex string.

## Framing

One record carries one complete handshake message; the handshake bytes are
`blob[5:5+record_length]`.

## Worked example (v1 hashes — will not reproduce under v2)

```
ja3      = "769,4865-4866-49195,0-10-11,23-24,0"
ja3_hash = "1a6e4c899214c0d5d9779f747252cbd4"
```
