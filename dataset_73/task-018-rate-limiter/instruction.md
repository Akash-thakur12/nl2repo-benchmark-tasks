# Multi-Tenant Rate Limiter — Token Bucket + Sliding Window

## 1. Overview

Re-implement the limiter that sits in the edge gateway's request path. Standard
library only; code in `engine/`. There are two independent per-key limiters:

- a **leaky token bucket** (`allow` / `tokens`), and
- a **sliding-window** request counter (`sliding_window`).

Time is supplied by `config["clock"]`, a zero-argument callable returning
seconds (default `time.time`). On the gateway this is host wall time, which is
NTP-disciplined and is **not** guaranteed to move forward. Passing a fake clock
makes behaviour fully deterministic.

Capacity and refill rate are not global constants: the gateway is multi-tenant
and the control plane publishes per-tenant policy rows that change over time.
`config["policies"]` carries those rows.

### What ships with this task

| path                                     | what it is                                                       |
|------------------------------------------|------------------------------------------------------------------|
| `environment/docs/limiter-contract.md`   | **Normative.** Key format, policy row shape, cost and clock rules. |
| `environment/reference/policies.json`    | A real control-plane export; traces 02 and 05 were captured against it. |
| `environment/capture/*.jsonl`            | Decision captures taken off gateway 4.3. **Authoritative.**       |
| `environment/capture/README.md`          | The capture file format and the gateway changelog.                |
| `environment/docs/incident-8812.md`      | A postmortem from an earlier gateway version.                     |
| `environment/tools/limiter_doctor.py`    | An unsupported internal triage script.                            |

Where any prose in this repository disagrees with a capture, the capture is
what the gateway does and the capture is what you must reproduce.

## 2. Public API — `engine/engine.py`

### `class RateLimiterEngine`

- `__init__(self, config=None)` — `config` keys:
  - `capacity` (int, default `10`)
  - `rate` (tokens per second, default `1.0`; `0.0` disables refill)
  - `clock` (callable, default `time.time`)
  - `policies` (optional list of control-plane rows — see the contract). When
    it is absent, `capacity` and `rate` describe the one policy that applies to
    every key.
- `allow(self, key: str, cost: int = 1) -> bool` — bring the key's bucket up to
  date for the time that has passed since it was last touched, then charge
  `cost` tokens against it if the bucket can pay. Returns whether the call was
  allowed. A key that has not been seen before starts with a full bucket.
- `tokens(self, key: str) -> float` — the key's token level, brought up to date
  the same way.
- `sliding_window(self, key: str, window_sec: float, max_reqs: int) -> bool` —
  admits at most `max_reqs` calls per key within a trailing window `window_sec`
  seconds wide. An admitted call is recorded on the key's timeline; a denied
  call is not recorded. Returns whether the call was admitted. This limiter is
  completely independent of the token bucket.
- `reset(self)` — drop all buckets and windows.
- `configure(self, options)` — apply `capacity` / `rate` / `clock` / `policies`
  from `options`, then `reset()`.

### `engine/bucket.py`

Holds `TokenBucket(capacity, refill_rate, now)` with `take(cost, now) -> bool`
and `level(now) -> float`. Keep those names and that signature; you may add
optional parameters.

```python
clock = lambda: t                       # t is your test's fake time
e = RateLimiterEngine({"capacity": 3, "rate": 0.0, "clock": clock})
e.allow("acme:10.0.0.1")
e.tokens("acme:10.0.0.1")
e.sliding_window("acme:10.0.0.1", window_sec=10, max_reqs=3)
```

## 3. What the documentation does not tell you

The contract fixes the shapes; it does not fix the behaviour. Four things are
specified only by the captures, and each one has exactly one answer:

1. **Which policy row governs a key at a given instant.** The export is an
   append-only log with backfilled rows, scheduled rows and amended publishes
   in it. `capture/trace-02-policy-rollout.jsonl` records what the gateway
   actually charged each tenant, per key, at known instants.
2. **What happens to a bucket that sat idle while its policy changed.** A
   bucket is only touched when a request arrives, so an idle span can straddle
   one or more policy changes. `capture/trace-05-downgrade.jsonl` records token
   levels either side of one edge and of two, in both directions, and records
   what a `cost` larger than the tenant's capacity does.
3. **What the limiter does when the clock steps backwards.**
   `capture/trace-03-clock-step.jsonl` records the bucket and the window either
   side of a real NTP correction. The two behaviours are recorded separately so
   they can be read off one at a time.
4. **Where the sliding window's trailing edge falls.**
   `capture/trace-04-window-boundary.jsonl` probes it from both sides.

Read `capture/README.md` first — it says which gateway version each artifact
belongs to.

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0. The suite
grades as a pass ratio, so partial correctness earns partial credit.
