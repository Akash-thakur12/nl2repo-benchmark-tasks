# Capture and report format

This document fixes the two things the tool cannot choose for itself: the shape
of what it reads and the shape of what it writes. Everything else - how an
assignment is actually decided - is described in prose in the brief and is
yours to design.

## Capture

A capture file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, read in file order. The first record is always `config`.

### `config`

```json
{"op": "config", "salt": "2026-Q1"}
```

### `experiment`

```json
{"op": "experiment", "key": "checkout-button", "state": "running",
 "traffic": 50, "exclusion_group": "checkout",
 "variants": [{"name": "control", "weight": 50},
              {"name": "treatment", "weight": 50}],
 "exclude": ["staff-1", "staff-2"]}
```

- `state` is `running`, `stopped` or `draft`.
- `traffic` is a whole percentage from 0 to 100.
- `variants` is a non-empty list; weights are non-negative whole numbers that
  sum to 100.
- `exclusion_group` and `exclude` may be absent.

### `assign`

```json
{"op": "assign", "user": "u-0001", "experiment": "checkout-button"}
```

### `end`

Always the last record.

## Report

One JSON object keyed by capture file name with `.experiments` stripped. Each
value has exactly these three keys:

```json
{
  "assignments": [
    {"user": "u-0001", "experiment": "checkout-button",
     "variant": "treatment", "reason": "ASSIGNED"},
    {"user": "staff-1", "experiment": "checkout-button",
     "variant": null, "reason": "EXCLUDED"}
  ],
  "summary": [
    {"experiment": "checkout-button",
     "variants": [{"variant": "control", "count": 12},
                  {"variant": "treatment", "count": 9}],
     "unassigned": 4}
  ],
  "errors": [{"code": "UNKNOWN_EXPERIMENT", "detail": "no-such-key"}]
}
```

- `assignments` is in request order, one entry per `assign` record.
- `variant` is a variant name, or `null` when nobody was assigned.
- `reason` is one of `ASSIGNED`, `EXCLUDED`, `NOT_IN_TRAFFIC`, `STOPPED`,
  `NOT_STARTED`, `MUTUALLY_EXCLUDED`, `UNKNOWN_EXPERIMENT`.
- `summary` lists every declared experiment, in the order the capture declares
  them, each with a count per declared variant in the order the experiment
  declares them, and `unassigned`, the number of requests for it that got no
  variant.
- `errors` has `code` and `detail`; the only code is `UNKNOWN_EXPERIMENT`.
