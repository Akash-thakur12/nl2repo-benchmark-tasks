# SRE Telemetry Incident Root-Cause Classifier

## 1. Overview

Platform hosts stream telemetry to a collector. When an incident opens, the
on-call tooling captures a window of those samples and needs a single
root-cause verdict for it, so the page routes to the right rotation.

Your job is to implement that classifier as a small engine class.

The classification behaviour is **specified by the documents that ship in
`environment/docs/`**, not by this file. This file defines the API surface and
the shape of the output; the docs define what the output must contain. Read all
of them before writing code — they are short, they cross-reference each other,
and more than one of them constrains the answer. `environment/samples/` holds
reviewed incident captures with the verdict the on-call engineer actually saw;
a correct implementation reproduces every one of them.

Standard library only; code in `engine/`.

## 2. Public API — `engine/engine.py`

### `class SreDiagEngine`

- `__init__(self, config=None)` — `config` is accepted and ignored.
- `add(self, t, cpu, mem, disk, net, gc)` — ingest one telemetry sample.
  `t` is a timestamp in epoch seconds; the other five are readings from the
  host agent. `environment/docs/collector-agent.md` documents which platform
  metric series each parameter carries, and what a consumer is obliged to do
  with the stream before analysing it.
- `diagnose(self) -> dict` — classify the samples ingested so far and return a
  verdict dict. See section 3.
- `reset(self)` / `configure(self, options)` — both return the engine to the
  empty state, discarding all ingested samples.

## 3. Verdict shape

`diagnose()` returns a dict with a `"cause"` key whose value is one of:

```
"INSUFFICIENT_DATA"   "DISK_IO_SATURATION"   "NET_SATURATION"
"CPU_BOTTLENECK"      "MEM_PRESSURE"         "NO_FAULT"
```

Some verdicts carry additional keys — `"secondary"` and/or `"cpu_suspect"`.
Which verdicts carry which keys, when a key is present at all, and what its
value is, are all specified by the in-force runbook in `environment/docs/`.
Do not emit keys the runbook does not call for, and do not omit keys it does.

Booleans are real Python booleans (`is False` / `is True` must hold), not 0/1.

## 4. Authority

`environment/` contains more than one document that talks about classification,
and they do not all agree. Some of what is on disk is retired, stale, or was
written against an older version of the rules. Each document declares its own
status. Work out which one is in force before you implement it; the reviewed
captures in `environment/samples/` are the tiebreak of last resort.

## 5. Determinism

`diagnose()` is a pure function of the samples ingested since construction or
since the last `reset()` / `configure()`. Calling it twice with no intervening
`add()` returns the same verdict, and it must not mutate the ingested samples.

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
