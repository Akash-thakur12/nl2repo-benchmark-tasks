# Sign-in capture format

A capture file is a single UTF-8 JSON object.

```json
{
  "max_speed_kmh": 900,
  "speed_policy": [
    {"from_t": 600000, "kmh": 80},
    {"from_t": 0, "kmh": 900}
  ],
  "dedup_window_seconds": 300,
  "locations": {
    "london": {"x": 0, "y": 0},
    "berlin": {"x": 930, "y": 0},
    "harbour": [
      {"from_t": 400000, "x": 1800, "y": 0},
      {"from_t": 0, "x": 0, "y": 0}
    ]
  },
  "events": [
    {"id": "e1", "t": 0, "user": "ada", "session": "s1",
     "location": "london", "outcome": "success"},
    {"id": "e2", "t": 60, "user": "ada", "session": "s2",
     "location": "harbour", "outcome": "success"}
  ]
}
```

- `max_speed_kmh` - a positive integer. It is the limit only when the capture
  carries no `speed_policy`; see `docs/location-registry.md`.
- `speed_policy` - optional. The travel policy as exported from the site
  register: a list of `{"from_t", "kmh"}` entries. When present it governs, and
  `docs/location-registry.md` is normative for resolving it.
- `dedup_window_seconds` - a non-negative integer.
- `locations` - name to coordinates in kilometres. An entry is **either** a
  plain `{"x", "y"}` object, for a site that has never moved, **or** a list of
  `{"from_t", "x", "y"}` revisions, for one that has. `docs/location-registry.md`
  is normative for which revision applies to which event; both shapes occur in
  the same capture and a tool must read both.
- `events` - each has `id`, `t` (whole seconds), `user`, `session`, `location`
  and `outcome`, which is `"success"` or `"failure"`. Events appear in whatever
  order the log was written.

A location name is known when `locations` has an entry for it, whichever shape
that entry takes.

## Report

The tool writes one JSON object keyed by capture file name with `.capture`
stripped. Each value has exactly these four keys:

```json
{
  "accepted": ["e1", "e2"],
  "duplicates": [],
  "impossible": [
    {"id": "e2", "user": "ada", "from": "london", "to": "harbour",
     "km": 1800, "seconds": 60}
  ],
  "errors": [{"code": "UNKNOWN_LOCATION", "detail": "atlantis"}]
}
```

- `accepted` - event ids, in consideration order
- `duplicates` - event ids, in consideration order
- `impossible` - one entry per flagged sign-in, in consideration order, with
  `id`, `user`, `from`, `to` (the site names, not their coordinates), `km` and
  `seconds`
- `errors` - in consideration order, with `code` (`UNKNOWN_LOCATION`) and
  `detail`, the location name
