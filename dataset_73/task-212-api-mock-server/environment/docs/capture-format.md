# Capture format

A capture file is a single UTF-8 JSON object.

```json
{
  "routes": [
    {
      "method": "GET",
      "path": "/users/{id}",
      "query": [{"name": "verbose", "type": "bool", "required": false}],
      "fixtures": [
        {"when": {"id": "1"}, "status": 200, "body": {"name": "ada"}},
        {"status": 404, "body": {"error": "not_found"}}
      ]
    },
    {
      "method": "POST",
      "path": "/users",
      "body": [{"name": "name", "type": "string", "required": true}],
      "allow_unknown": false,
      "fixtures": [{"status": 201, "body": {"created": true}, "times": 1}]
    }
  ],
  "reloads": [
    {
      "at": 4103,
      "routes": [
        {"method": "GET", "path": "/users/{id}",
         "fixtures": [{"status": 200, "body": {"name": "grace"}}]}
      ]
    }
  ],
  "requests": [
    {"method": "GET", "path": "/users/1", "seq": 4102,
     "query": {"verbose": "true"}},
    {"method": "POST", "path": "/users", "seq": 4101, "body": {"name": "ada"}},
    {"method": "GET", "path": "/users/1", "seq": 4103}
  ]
}
```

- `routes` - ordered. Each has `method`, `path`, `fixtures`, and optionally
  `query`, `body` and `allow_unknown`. This is the contract the mock was
  serving when the recording began.
- `query` and `body` - ordered lists of `{name, type, required}`.
- `fixtures` - ordered. Each has `status` and `body`, and optionally `when`
  (path parameter values) and `times`.
- `reloads` - optional, ordered by `at`. The mock watches its contract file and
  reloads it in place, so a capture taken across a deploy carries more than one
  contract. Each entry has an `at` (a request counter value inside this
  capture's run) and a `routes` list with the same shape as the top-level one.
  A reload replaces the route list outright; it is not merged into the
  previous one.
  TODO(platform): document how `reloads` lines up with the request counter; the
  recordings in `reference/` are the record for now.
- `requests` - ordered. Each has `method`, `path` and `seq`, and optionally
  `query` (an object of strings) and `body` (an object).

## The request counter

`seq` is the value of the mock's request counter when it handled that request.
The counter is 16-bit: it increases by one per request handled and wraps from
65535 back to 0. A capture holds one unbroken run of the counter - every value
from the first request the collector saw to the last, with none missing and none
repeated.

`requests` is in the order the collector's workers flushed them, which is not
the order the mock handled them.

## Report

The tool writes one JSON object keyed by capture file name with `.capture`
stripped. Each value has exactly these two keys:

```json
{
  "responses": [
    {"status": 200, "body": {"name": "ada"}, "headers": {}},
    {"status": 405, "body": {"error": "method_not_allowed"},
     "headers": {"allow": "POST, PUT"}}
  ],
  "matched": [0, null]
}
```

- `responses` - one per request, in the order `requests` lists them, each with
  `status`, `body` and `headers`
- `matched` - the index of the route that answered each request, or `null`
