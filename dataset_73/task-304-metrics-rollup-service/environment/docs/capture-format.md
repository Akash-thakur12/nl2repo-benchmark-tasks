# Capture format

A capture file is a single UTF-8 JSON object.

```json
{
  "tiers": [
    {"name": "1m", "seconds": 60},
    {"name": "5m", "seconds": 300}
  ],
  "samples": [
    {"t": 0,  "name": "http_requests", "labels": {"code": "200"},
     "type": "counter", "value": 10},
    {"t": 30, "name": "queue_depth", "labels": {},
     "type": "gauge", "value": 5},
    {"t": 30, "name": "latency", "labels": {"route": "/a"}, "type": "histogram",
     "boundaries": [10, 50, 100], "counts": [3, 1, 0]}
  ]
}
```

- `tiers` - ordered, shortest window first. Each has `name` and `seconds`.
- `samples` - each has `t` (whole seconds), `name`, `labels`, `type`
  (`"counter"`, `"gauge"` or `"histogram"`), and either `value` (an integer, for
  counters and gauges) or `boundaries` and `counts` (integer arrays, for
  histograms).

Samples appear in the capture in whatever order the collector wrote them; they
are not necessarily sorted by `t`.

## Report

The tool writes one JSON object keyed by capture file name with `.capture`
stripped. Each value has exactly these two keys:

```json
{
  "rows": [
    {"tier": "1m", "series": "http_requests,code=200", "type": "counter",
     "window": 0, "delta": 0},
    {"tier": "1m", "series": "queue_depth", "type": "gauge", "window": 0,
     "min": 5, "max": 5, "last": 5, "count": 1, "sum": 5, "avg": 5},
    {"tier": "1m", "series": "latency,route=/a", "type": "histogram",
     "window": 0, "boundaries": [10, 50, 100], "counts": [3, 1, 0]}
  ],
  "errors": [{"code": "BUCKET_MISMATCH", "series": "latency,route=/b"}]
}
```

- `rows` - ordered by tier as configured, then by series key ascending, then by
  window start ascending. Every value is an integer.
- `errors` - one entry per affected series, ordered by series key, with `code`
  and `series`.
