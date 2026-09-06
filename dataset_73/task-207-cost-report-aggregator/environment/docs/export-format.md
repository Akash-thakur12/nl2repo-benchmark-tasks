# Export capture format

An export file is a single UTF-8 JSON object.

```json
{
  "period": {"start": 0, "end": 29},
  "teams": ["alpha", "beta"],
  "shared_weights": {"alpha": 3, "beta": 1},
  "weight_changes": [{"day": 12, "weights": {"alpha": 1, "beta": 1}}],
  "renamed_from": {"bravo": "beta"},
  "lines": [
    {"id": "l1", "kind": "usage", "day": 5, "team": "alpha", "cents": 1000},
    {"id": "l2", "kind": "usage", "day": 5, "team": null, "cents": 500},
    {"id": "l3", "kind": "shared", "day": 5, "cents": 101},
    {"id": "l4", "kind": "reservation", "day": -2, "term_days": 10,
     "cents": 1000, "team": "beta"},
    {"id": "l5", "kind": "credit", "day": 10, "team": "alpha", "cents": 300}
  ]
}
```

- `period` - `start` and `end`, inclusive whole days.
- `teams` - every team the report covers, in whatever order.
- `shared_weights` - team name to a non-negative integer weight. May be absent
  or empty. This is the split configured for the start of the period.
- `weight_changes` - optional array of amendments to the split, each an object
  with a `day` and a `weights` map of the same shape as `shared_weights`. The
  array is in the order finance filed the amendments, which is not necessarily
  ascending by `day`, and two entries may carry the same `day`. May be absent or
  empty. `docs/weights-and-renames.md` reconciles four billed lines against it.
- `renamed_from` - optional map from a retired team name to the name it became.
  The collector still stamps retired names on lines and in weight maps; this map
  is the only record of the correspondence. May be absent or empty.
  `docs/weights-and-renames.md` reconciles four more billed lines against it.
- `lines` - ordered. Every line has `id`, `kind` and `day`. A `usage` line has
  `team` (possibly `null`) and `cents`. A `shared` line has `cents`. A
  `reservation` line has `team`, `cents` and `term_days`. A `credit` line has
  `team` and `cents`.

## Report

The tool writes one JSON object keyed by export file name with `.export`
stripped. Each value has exactly these four keys:

```json
{
  "teams": {
    "alpha": {"usage": 1000, "amortised": 0, "shared": 76, "credit": 300,
              "total": 776},
    "beta": {"usage": 0, "amortised": 800, "shared": 25, "credit": 0,
             "total": 825}
  },
  "unallocated": 500,
  "unused_credit": 0,
  "errors": [{"code": "DUPLICATE_LINE", "detail": "l1"}]
}
```

- `teams` - one entry per configured team, each with `usage`, `amortised`,
  `shared`, `credit` and `total`
- `unallocated` - money that reached no team
- `unused_credit` - credit that could not be applied
- `errors` - in line order, with `code` (`DUPLICATE_LINE` or `UNKNOWN_TEAM`) and
  `detail`, the line id or the team name
