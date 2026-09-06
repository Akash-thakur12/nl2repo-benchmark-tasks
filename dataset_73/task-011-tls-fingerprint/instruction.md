# TLS ClientHello Dissector & JA3 Fingerprint

## 1. Overview

Parse a raw TLS handshake capture carrying a **ClientHello** and compute a
*simplified* JA3 fingerprint. Standard library only; code in `engine/`.
`engine/parser.py` provides `TLS_RECORD_HANDSHAKE` (0x16) and
`TLS_HANDSHAKE_CLIENT_HELLO` (0x01).

The fingerprint format is specified by the documents under `docs/` and pinned by
the capture corpus in `corpus/`; `tools/ja3_diff.py` replays that corpus against
your engine.

## 2. Record / ClientHello layout parsed

```
record:   type(1)=0x16 | version(2) | length(2) | payload bytes
handshake: msg_type(1)=0x01 | length(3) | client_version(2) | random(32)
           | session_id_len(1) | session_id(...)
           | cipher_suites_len(2) | cipher_suites(2 bytes each)
           | compression_methods_len(1) | compression_methods(...)
           | [ extensions_len(2) | { ext_type(2) ext_len(2) ext_data } * ]
```

Two extensions are decoded further:
- `0x000A` supported groups / "elliptic curves": `list_len(2)` then `u16` ids.
- `0x000B` EC point formats: `count(1)` then that many `u8` formats.

## 3. Simplified JA3

`ja3` is the five parsed values — version, cipher suites, extension types,
supported groups, EC point formats — joined into one comma-separated string;
`ja3_hash` is `md5(ja3)` as a lowercase hex string. Which bytes each field is
taken from, how the lists are ordered, how an empty list is written and which
values are excluded before joining are specified in
`docs/ja3-v2-field-notes.md`, and every rule there is pinned by
`corpus/expected.csv`, which carries one row per capture with each field in its
own column.

## 4. Public API — `engine/engine.py`

### `class TlsFingerprintEngine`

- `__init__(self, config=None)` — `config` accepted and ignored.
- `parse(self, raw) -> dict` — `raw` is `bytes` or a hex `str` holding the
  captured record stream. Returns:
  ```python
  {
    "version": int,
    "ciphers": list[int],
    "extensions": list[int],
    "curves": list[int],
    "point_formats": list[int],
    "ja3": str,
    "ja3_hash": str,             # md5(ja3) hex
  }
  ```
  The five list/int entries hold exactly the values that go into the
  corresponding `ja3` field, in the same order.

  Raises `ValidationError` if the buffer is shorter than 5 bytes, the record
  type is not `0x16`, the handshake message type is not `0x01` (ClientHello), or
  a length field runs off the end of the available bytes.
- `reset(self)` / `configure(self, options)` — no-ops (stateless).

### Exception

- `ValidationError` (subclass of `ValueError`, defined in `engine/engine.py`).

## 5. Determinism

`parse` is a pure function of its input bytes.

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
