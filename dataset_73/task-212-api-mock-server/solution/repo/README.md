# mockserver

Answers a captured sequence of requests from a contract, the way the mock
server would have, without opening a socket.

    ./run.sh <capture_dir> <output_json>

Four things about this are easy to get wrong and are worth stating up front.

- A request that matches a path but not a method is a 405 with an `allow`
  header, never a 404. The header lists the methods the candidates *answer*,
  so a GET candidate puts `HEAD` in it too.
- Two overlapping templates are compared segment by segment from the left, and
  the leftmost segment where one is a literal and the other a parameter decides
  it. A count of literal segments is not the rule: see rows 1 to 3 of
  `docs/gateway-routing.md`, where the template with three literals loses to
  the one with one.
- A capture is written in the order the collector's workers flushed it, and its
  `seq` values are a 16-bit counter that can wrap inside a single capture. The
  mock handled the requests in counter order, so everything it carries between
  requests - fixture tallies, which contract is loaded - has to be replayed in
  that order. The report itself stays in file order.
- A request is answered by the contract in force at its own counter value, not
  by the last contract in the file. A reload replaces the route list outright,
  so `matched` is an index into whichever list was loaded then, and the new
  list's fixtures start unused.

## Layout

    mockserver/routing.py     path templates, precedence, and which methods a
                              route answers
    mockserver/validation.py  query and body schemas
    mockserver/server.py      the counter, the contract in force, fixture
                              selection and the request loop
    mockserver/__main__.py    directory walk and JSON output

Behaviour is specified in `docs/mock-spec.md`, with `docs/gateway-routing.md`
normative for precedence and the recordings in `reference/` normative for what
the specification leaves open. Section numbers appear in comments beside the
rule each piece implements.

`devtools/contract_lint.py` in the task image is a pre-commit helper the
platform team keeps, not a description of the mock; its shadowing heuristic and
its comment about replay order are both out of date.
