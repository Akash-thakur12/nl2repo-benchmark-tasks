# Onion-Routing Relay Cell Protocol

## 1. Overview

Process onion-routing relay cells: a **layered stream cipher**, fixed-size cell
payloads, and classification of a peeled cell as *recognized* (this hop is the
destination for the payload) vs *relay-forward*. Standard library only; code in
`engine/`.

`engine/cells.py` provides `CELL_PAYLOAD_LEN` (498), `RECOGNIZED_MARKER` (`b"OK"`)
and `LEN_FIELD` (2).

## 2. Cipher

Per-hop keystream (SHA-256 in counter mode):

```
keystream(key, n) = ( sha256(key + 0) || sha256(key + 1) || ... )[:n]
```
where each counter is an 8-byte big-endian integer. Encryption / decryption is
`data XOR keystream(key, len(data))`. (This is a stream cipher, so applying two
hops' layers commutes — order of keys does not matter, only the set.)

## 3. Cell layout (plaintext, before encryption)

```
RECOGNIZED_MARKER (2 bytes = b"OK") | payload_len (2 bytes BE) | payload | zero padding
```
padded with `\x00` to exactly `CELL_PAYLOAD_LEN` bytes, then encrypted.

## 4. Public API — `engine/engine.py`

### `class TorRelayEngine`

- `__init__(self, config=None)` — starts with no circuit keys.
- `register_circuit(self, circ_id: int, hop: int, key: bytes)` — store the key
  for one `(circuit, hop)`.
- `make_cell(self, circ_id, hop, payload: bytes) -> bytes` — build and encrypt a
  single-layer cell for that hop. Raises `ValueError` if no key is registered, or
  if `payload` does not fit in one cell (`> CELL_PAYLOAD_LEN - 4`).
- `decrypt(self, circ_id, hop, cell: bytes) -> bytes | None` — decrypt one layer.
  Returns `None` if no key is registered or the result does not begin with
  `RECOGNIZED_MARKER`. On success marks `(circ_id, hop)` recognized and returns
  `RECOGNIZED_MARKER + payload` (the original payload, un-padded).
- `recognized(self, circ_id, hop) -> bool` — has a cell for that `(circuit, hop)`
  been successfully decrypted since the last `reset()` / `configure()`.
- `make_onion(self, circ_id, hops: list[int], payload) -> bytes` — wrap `payload`
  for a path: encrypt for `hops[-1]`, then wrap once with each earlier hop's key
  (outermost layer is `hops[0]`).
- `peel(self, circ_id, hops: list[int], cell) -> bytes | None` — remove every
  hop's layer in order and return `decrypt(circ_id, hops[-1], ...)`.
- `reset(self)` — clear the recognized set (keys are kept).
- `configure(self, options)` — clear keys **and** the recognized set.

## 5. Example

```python
r = TorRelayEngine()
r.register_circuit(101, 0, b"0" * 16)
cell = r.make_cell(101, 0, b"hello")
r.decrypt(101, 0, cell)     # -> b"OKhello"
r.recognized(101, 0)        # -> True
```

## 6. Determinism

`make_cell` / `make_onion` are pure functions of the registered keys and input.

## 7. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
