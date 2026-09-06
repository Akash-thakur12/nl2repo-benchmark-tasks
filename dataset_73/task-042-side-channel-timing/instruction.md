# Constant-Time Comparison & Timing-Leak Check

## 1. Overview

A constant-time equality primitive plus a check that tells a constant-time
comparator from an early-exit one. Standard library only; code in `engine/`.
`engine/timing.py` holds `safe_compare(a, b)` (a constant-time wrapper) and
`naive_compare(a, b)` (deliberately vulnerable — returns on the first differing
byte).

## 2. Public API — `engine/engine.py`

### `class SideChannelEngine`

- `__init__(self, config=None)` / `reset(self)` / `configure(self, options)` —
  stateless; no-ops.
- `compare(self, a, b) -> bool` — constant-time equality via
  `hmac.compare_digest`. `a` and `b` may be `str` or `bytes`; **operands of
  different types are never equal**, and a non-str/bytes operand yields `False`.
- `is_constant_time(self, fn=None, size=4096, trials=9, iters=400) -> bool` —
  returns whether `fn` (default: this engine's `compare`) runs in time
  independent of *where* two equal-length inputs first differ. It times `fn` on
  (a) two identical `size`-byte inputs and (b) inputs differing at byte 0, taking
  the median of `trials` batches of `iters` calls, and returns
  `max/min ratio < 4.0`. `hmac.compare_digest` and `safe_compare` (and `None`)
  are recognised as constant-time directly.

## 3. Example

```python
sec = SideChannelEngine()
sec.compare(b"secret", b"secret")      # -> True
sec.compare("secret", b"secret")       # -> False (mixed types)
sec.is_constant_time()                 # -> True
sec.is_constant_time(naive_compare)    # -> False
```

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
