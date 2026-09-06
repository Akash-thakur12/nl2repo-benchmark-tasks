Our front-end teams test against a mock of our API, and every sprint someone
finds that the mock is kinder than the real service: it accepts a body the real
one rejects, or answers a path the real one has never heard of. We want the mock
driven by the contract, and we want to be able to see exactly what it would have
answered before we point anyone at it.

Build the replay tool. Given a directory of captured contracts and request
sequences it should report the response the mock would give to each request, and
which route answered it.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <capture_dir> <output_json>

It must process every `*.capture` file in `<capture_dir>` and write a single
JSON object to `<output_json>`. It must not open a socket. Structure the
repository however you think is right; only `run.sh` and the report are
contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the mock behaves

The rules are specified in `/app/docs/mock-spec.md`. The capture format and the
exact report schema are in `/app/docs/capture-format.md`. Route precedence is
recorded in `/app/docs/gateway-routing.md`. All three are normative: where this
file and those disagree, those win.

`/app/samples/` holds six captures (`s01.capture` ... `s06.capture`) together
with the correct report for them, `/app/samples/expected.json`.

`/app/reference/` holds eight captures (`r01.capture` ... `r08.capture`)
recorded from the live mock, together with the report it produced,
`/app/reference/recorded.json`. Unlike the samples, these were chosen to pin
down the things the specification does not spell out.

`/app/devtools/` holds a script the platform team keeps for its own use. It is
not part of the mock.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.capture` file, each value an
   object with exactly the two keys `responses` and `matched`, one entry each
   per request.
3. For every capture, every response status matches.
4. For every capture, every response body and header matches.
5. For every capture, `matched` matches.
6. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.
7. Running the tool on `/app/reference` reproduces
   `/app/reference/recorded.json` exactly.

## Notes

The samples come from a contract with nothing tricky in it: one route per path,
no two templates able to match the same request, no query or body schema, one
fixture per route, `GET` and `POST` only, a single contract for the whole
capture, and a request counter that runs straight up in file order. Real
captures use everything the specification and the capture format describe, so
reproducing `expected.json` is necessary but a long way from sufficient. The
recordings in `/app/reference/` are not benign in any of those ways, which is
why criterion 7 is separate from criterion 6.

Use only the Python standard library.
