# Limiter contract — keys, policy rows, and what is normative

Status: normative for gateway 4.x. Owner: edge-platform.

This document fixes the *shapes* the limiter deals in: how a key is spelled and
what a control-plane policy row contains. It deliberately does **not** state how
a row is selected for a given request — see "Resolution" below.

## 1. Keys

A limiter key is a string. The gateway builds it as

```
<tenant>:<client-id>
```

- The **tenant** is the substring before the **first** `:` in the key. Client
  ids frequently contain colons of their own (`acme:10.0.0.7:443`,
  `acme:tok:9f2a`); only the first separator is structural.
- A key with no `:` at all names no tenant. Internal probes are spelled this
  way (`healthcheck`, `readyz`).
- Tenant names are matched exactly and are case-sensitive.

Every key gets its own token bucket and its own sliding-window timeline. Two
keys belonging to the same tenant share a *policy*, never a bucket.

## 2. Control-plane policy rows

`config["policies"]` is the `policies` array of a control-plane export, passed
through unchanged. A row is:

```json
{"tenant": "acme", "capacity": 12, "rate": 0.05,
 "effective_at": 1735690800, "revision": 4,
 "note": "acme post-incident settings"}
```

| field          | type    | meaning                                                       |
|----------------|---------|---------------------------------------------------------------|
| `tenant`       | string  | the tenant the row applies to, or `"*"` for the platform default |
| `capacity`     | number  | bucket capacity, in tokens                                    |
| `rate`         | number  | refill rate, in tokens per second (`0` disables refill)       |
| `effective_at` | number  | epoch seconds; the instant from which this row is in force    |
| `revision`     | integer | the control plane's monotonically increasing publish counter  |
| `note`         | string  | free text from the operator; carries no meaning to the gateway |

Facts about real exports that implementations have tripped over:

- The array is ordered by `revision`, **not** by `effective_at`. Its order
  carries no other meaning.
- `revision` is a publish counter, so a row published later can be effective
  earlier: the control plane backfills rows for periods it failed to record,
  and schedules rows for periods that have not happened yet. Both land in the
  same export as everything else.
- A publish can be amended. When it is, the corrected row is a **new** revision
  carrying the **same** `effective_at` as the row it corrects. Both rows stay in
  the export; the export is an append-only log, not a current-state view.
- `effective_at` values are absolute epoch seconds on the same timebase as the
  clock the limiter is given.

### Tenants with no row

A tenant that appears nowhere in the export is governed by the `"*"` rows.
So is a key that names no tenant at all. So is a tenant whose rows exist but
none of which is in force at the instant being resolved.

The `"*"` tenant is itself an ordinary set of rows and changes over time like
any other.

### No `policies` at all

When `config` carries no `policies`, the engine's own `capacity` and `rate`
behave as a single `"*"` row that has been in force since before any timestamp
the limiter can be shown. This is the configuration `trace-01-baseline.jsonl`
was captured under.

## 3. Resolution

Given a key and an instant, exactly one row governs. **The rule that picks it is
not specified here.** It is specified by the gateway's own behaviour, and the
authoritative record of that behaviour is
`../capture/trace-02-policy-rollout.jsonl`, captured against
`../reference/policies.json`. An implementation is correct when it reproduces
that capture line for line; nothing else about resolution is normative.

The same applies to how a bucket's stored token level interacts with a policy
that changed while the bucket sat idle — `../capture/trace-05-downgrade.jsonl`
is the record — and to how the limiter behaves when the host clock is corrected
— `../capture/trace-03-clock-step.jsonl` is the record.

This is deliberate. Between 3.8 and 4.0 the prose in this document and the
gateway's behaviour disagreed for six weeks, and every consumer had written
their client against the prose.

## 4. Clock

The limiter is given a zero-argument callable returning seconds. On the gateway
this is host wall time, disciplined by NTP. It is **not** monotonic: a step
correction moves it, and the January 2026 correction moved it backwards. The
limiter is expected to keep serving through that without an operator touching
it.

## 5. Cost

`allow(key, cost)` charges `cost` tokens. `cost` is an integer number of tokens
and may exceed the capacity of the governing policy; the gateway does not
validate it upstream, and a request the bucket could never satisfy must still
produce a decision rather than an error or a wait.
