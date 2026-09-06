# Mock server specification

This document specifies how a contract-driven mock answers a request. The
replay tool must reproduce it exactly.

## 1. Routes

**1.1** A route has a `method`, a `path` template, optional `query` and `body`
schemas, and one or more `fixtures`.

**1.2** A path template is a sequence of `/`-separated segments. A segment
wrapped in braces, like `{id}`, is a parameter and matches exactly one segment.
Every other segment is a literal and must match exactly, case-sensitively.

**1.3** A request path matches a template when they have the same number of
segments and every literal agrees. A leading `/` is not a segment, and a
trailing `/` produces a final empty segment that must be matched.

## 2. Choosing a route

**2.1** Every route whose path template matches is a candidate, whatever its
method.

**2.2** If there are no candidates the response is `404` with body
`{"error": "no_route"}`.

**2.3** Among candidates, those that answer the request's method are
considered. If none does, the response is `405` with body
`{"error": "method_not_allowed"}` and an `allow` header listing the methods the
candidates answer, sorted and joined with `, `.

**2.4** Two candidates can both match the same request. Among the remaining
candidates exactly one answers. The mock must resolve an overlap the way the
production gateway resolves it; `docs/gateway-routing.md` records the gateway's
decisions and is normative.

## 3. Validating the query

**3.1** A query schema names parameters, each with a `type` (`string`, `int` or
`bool`) and a `required` flag.

**3.2** A required parameter that is absent gives `400` with body
`{"error": "missing_query", "name": "<name>"}`.

**3.3** A parameter present but not parseable as its type gives `400` with body
`{"error": "bad_query", "name": "<name>"}`. An `int` is an optional `-` followed
by digits and nothing else. A `bool` is exactly `true` or `false`.

**3.4** Parameters are checked in the order the schema declares them, and the
first failure is the response.

**3.5** A parameter the schema does not name is ignored.

## 4. Validating the body

**4.1** A body schema names fields, each with a `type` (`string`, `int`, `bool`
or `object`) and a `required` flag.

**4.2** A required field that is absent gives `400` with body
`{"error": "missing_field", "name": "<name>"}`.

**4.3** A field whose value is not of its type gives `400` with body
`{"error": "bad_field", "name": "<name>"}`. Types are strict: `true` is not an
`int`, and `1` is not a `string`.

**4.4** Fields are checked in schema order, and the first failure is the
response. The query is validated before the body.

**4.5** A field the schema does not name is rejected with `400` and body
`{"error": "unknown_field", "name": "<name>"}`, unless the route sets
`allow_unknown`. Unknown fields are checked after every declared field has
passed, in ascending field name order.

## 5. Choosing a fixture

**5.1** A route's fixtures are tried in order. A fixture with a `when` matches
when every named path parameter equals the value given. A fixture without a
`when` always matches.

**5.2** The first matching fixture answers the request.

**5.3** If no fixture matches, the response is `404` with body
`{"error": "no_fixture"}`.

**5.4** A fixture that has already answered `times` requests is skipped, so a
route can answer differently on a second call. A fixture without `times`
never runs out.

## 6. Report

**6.1** `responses` lists one entry per request, in order, each with `status`,
`body` and `headers`. `headers` is an object, empty unless the specification
says otherwise.

**6.2** `matched` lists, for each request, the index of the route that answered
it, or `null` when none did. The index is into the route list the mock was
serving when it handled that request.

## 7. Order

**7.1** The mock handles requests in counter order. Every state the mock carries
between requests - which fixtures have already answered, and therefore which
fixture answers next under 5.4 - evolves in that order.

**7.2** The report lists responses in the order the capture lists the requests.

**7.3** `docs/capture-format.md` describes the counter, and how a capture
records the contract the mock was serving.

## 8. What is not written here

**8.1** The recordings in `reference/` were taken from the live mock and settle
anything this document leaves open. Where this document and a recording
disagree, the recording wins.

**8.2** `docs/gateway-routing.md` is normative for 2.4.

**8.3** Nothing under `devtools/` is normative. Those are convenience scripts
the platform team maintains for its own use; they are not the mock and they are
not always current.
