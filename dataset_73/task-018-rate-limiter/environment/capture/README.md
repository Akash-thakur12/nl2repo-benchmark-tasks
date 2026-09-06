# Gateway decision captures

These files are taken straight off the edge gateway's decision tap. They are
machine-generated: one JSON object per line, no post-processing, no editing.
When anything else in this repository disagrees with a capture, the capture is
right — it is a recording of what the gateway actually returned.

Every trace was captured on **gateway 4.3** (see the `gateway_version` field on
each header line, and the changelog at the bottom of this file).

## File format

UTF-8 JSON Lines. The first line of every file is the header; every line after
it is one call into the limiter, in the order the gateway made them. A single
limiter instance is used for the whole file, so state carries from line to line.

### Header line

```json
{"record": "header", "gateway_version": "4.3", "trace": "trace-01-baseline",
 "config": {"capacity": 10, "rate": 1.0}, "note": "..."}
```

`config` is the config the limiter was constructed with, minus the clock.
Where `config.policies` is the string `"reference/policies.json"`, the limiter
was constructed with the `policies` array out of that file, verbatim and in
file order.  A `config` with no `capacity`/`rate` used the engine defaults.

### `op: "allow"`

```json
{"record": "decision", "op": "allow", "t": 1735689600.0,
 "key": "acme:10.0.0.1", "cost": 1, "decision": true, "tokens_after": 9.0}
```

| field          | meaning                                                       |
|----------------|---------------------------------------------------------------|
| `t`            | what the injected clock returned for this call, in seconds     |
| `key`          | the limiter key, exactly as the gateway passed it              |
| `cost`         | the `cost` argument                                            |
| `decision`     | the boolean `allow()` returned                                 |
| `tokens_after` | the key's token level immediately after the call, 6dp          |

### `op: "tokens"`

```json
{"record": "probe", "op": "tokens", "t": 1735689603.0,
 "key": "acme:10.0.0.1", "tokens_after": 8.0}
```

A read-only probe the tap inserts. `tokens_after` is what `tokens(key)`
returned. Probes are ordinary calls as far as the limiter is concerned.

### `op: "window"`

```json
{"record": "decision", "op": "window", "t": 1735689600.0,
 "key": "globex:10.0.0.2", "window_sec": 10, "max_reqs": 3, "decision": true}
```

`window_sec` and `max_reqs` are the arguments; `decision` is what
`sliding_window()` returned. The sliding-window limiter and the token bucket
are independent — a `window` line never touches a bucket and vice versa.

## The traces

| file                            | what it covers                                              |
|---------------------------------|-------------------------------------------------------------|
| `trace-01-baseline.jsonl`       | one fixed capacity/rate, forward clock. The boring case.     |
| `trace-02-policy-rollout.jsonl` | control-plane rows in force; first-touch bursts per tenant.  |
| `trace-03-clock-step.jsonl`     | the 2026-01-01 NTP correction; the host clock steps back.    |
| `trace-04-window-boundary.jsonl`| window expiry probed either side of the window edge.         |
| `trace-05-downgrade.jsonl`      | buckets left idle across control-plane edges, both ways.     |

Traces 02 and 05 were captured against the export in
`../reference/policies.json`; the row shape and the key format are documented
in `../docs/limiter-contract.md`.

Each line in traces 02–05 was chosen by the capture harness to isolate one
mechanism, so a line that a candidate implementation gets wrong names the
mechanism it got wrong.

## Gateway changelog (limiter subsystem only)

| version | landed     | change                                                                                              |
|---------|------------|-----------------------------------------------------------------------------------------------------|
| 3.8     | 2025-09-11 | per-tenant policy rows introduced; a published row took effect immediately for everyone              |
| 3.9     | 2025-10-02 | incident 8812 mitigations (see `../docs/incident-8812.md`)                                           |
| 4.0     | 2025-11-14 | control-plane rows carry `effective_at`; an export is no longer applied at publish time. Behaviour is pinned by `trace-02-policy-rollout.jsonl`. |
| 4.1     | 2025-12-03 | decision tap emits `tokens_after` on every line; `tokens` probes added                               |
| 4.2     | 2025-12-19 | sliding-window expiry boundary corrected. Behaviour is pinned by `trace-04-window-boundary.jsonl`.   |
| 4.3     | 2026-01-08 | refill hardened against NTP corrections after the 2026-01-01 step. Behaviour is pinned by `trace-03-clock-step.jsonl`. |

Anything written before 4.0 describes a gateway that no longer exists. The
`../tools/limiter_doctor.py` triage script has not been updated since 3.9 and
is unsupported.
