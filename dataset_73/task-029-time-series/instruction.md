# Gorilla XOR Float Time-Series Compression

## 1. Overview

Compress a sequence of IEEE-754 doubles with Facebook's Gorilla value encoding
and decompress it losslessly. Standard library only; code in `engine/`.
`engine/compression.py` holds `float_to_bits` / `bits_to_float`, `BitWriter`
(`write_bit`, `write_bits(value, count)`, `getvalue`) and `BitReader`
(`read_bit`, `read_bits(count)`).

## 2. Format

`compress` returns `struct.pack(">I", len(values))` followed by the bitstream
(MSB-first within each byte, zero-padded at the end):

- The first value: 64 raw bits (`float_to_bits`).
- Each later value, `xor = bits ^ prev_bits`:
  - `xor == 0` -> write bit `0`.
  - else write bit `1`, then:
    - if a previous window exists and `leading_zeros(xor) >= prev_leading` and
      `trailing_zeros(xor) >= prev_trailing`: write bit `0`, then the
      `64 - prev_leading - prev_trailing` meaningful bits (`xor >> prev_trailing`).
    - otherwise write bit `1`, 5 bits of `leading` (capped at 31), 6 bits of
      `length = 64 - leading - trailing` (a length of 64 is stored as `0`), then
      the `length` meaningful bits. This becomes the new window.

`decompress` reads the count, then reverses the process.

## 3. Public API — `engine/engine.py`

### `class TimeSeriesEngine`
- `__init__(self, config=None)` — `config` accepted and ignored.
- `compress(self, values: list[float]) -> bytes`.
- `decompress(self, data: bytes) -> list[float]`.
- `reset(self)` / `configure(self, options)` — no-ops (stateless).

## 4. Guarantees the tests rely on

- `decompress(compress(v)) == v` for every input, including `NaN`, `inf`,
  `-inf`, `-0.0` (sign preserved) and extreme magnitudes.
- `compress([])` is exactly `b"\x00\x00\x00\x00"`.
- A constant series of 50 values compresses to well under `50 * 8` bytes; a
  slowly drifting series of 200 values is meaningfully smaller than raw.

## 5. Example

```python
ts = TimeSeriesEngine()
blob = ts.compress([100.5, 100.55, 100.52])
ts.decompress(blob)         # -> [100.5, 100.55, 100.52]
```

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
