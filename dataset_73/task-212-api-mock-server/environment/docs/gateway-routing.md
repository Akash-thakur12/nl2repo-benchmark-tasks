# Gateway routing decisions

Normative for `docs/mock-spec.md` section 2.4.

Two routes in a contract can both match the same request path. The production
gateway already has an answer for every such overlap, and the mock must give the
same one, so this file records the gateway's answers rather than restating its
implementation.

The table below is a dump of the gateway team's routing conformance suite. Each
row is a contract of two routes, given **in declaration order** as route 0 and
route 1, a request path both templates match, and the route the gateway
dispatched it to. The suite fixes the method of both routes to the request's
method, because the method plays no part here: the gateway applies the method
filter of section 2.3 first and only then resolves the overlap between whatever
candidates are left.

| # | route 0 | route 1 | request path | gateway dispatched to |
|---|---------|---------|--------------|-----------------------|
| 1 | `/{tenant}/settings/theme/mode` | `/acme/{a}/{b}/{c}` | `/acme/settings/theme/mode` | **1** |
| 2 | `/files/{bucket}/raw/{key}` | `/files/logs/{a}/{b}` | `/files/logs/raw/x` | **1** |
| 3 | `/v1/{c}/{d}/tail` | `/v1/{a}/logs/{b}` | `/v1/x/logs/tail` | **1** |
| 4 | `/{a}/{b}/c` | `/{x}/{y}/c` | `/p/q/c` | **0** |
| 5 | `/users/{id}` | `/users/me` | `/users/me` | **1** |
| 6 | `/users/me` | `/users/{id}` | `/users/me` | **0** |
| 7 | `/{a}/reports` | `/orders/{b}` | `/orders/reports` | **1** |
| 8 | `/a/{b}/{c}/d` | `/a/{b}/{c}/{z}` | `/a/x/y/d` | **0** |
| 9 | `/{a}/x/{c}` | `/{a}/{b}/z` | `/p/x/z` | **0** |
| 10 | `/logs/{a}/{b}/{c}` | `/{w}/{x}/{y}/{z}` | `/logs/1/2/3` | **0** |

## Two properties the gateway team guarantees

1. The gateway's choice between two candidate templates depends only on the two
   templates - never on the request path, and never on declaration order except
   between two templates of identical shape. (Two templates have the same shape
   when each of their segments is a parameter in both or a literal in both.
   Candidates always have the same number of segments, since they all matched
   the same request.)

2. With more than two candidates the gateway applies the same comparison to
   each pair, and dispatches to the one that beats every other. The comparison
   is a total order, so that route always exists and is unique.

## Notes from the ticket that produced rows 1-3

Rows 1, 2 and 3 are the regressions that motivated the suite. Each came in as a
bug report against a proposed "specificity score" - one that counted literal
segments, one that counted them and then fell back to declaration order, and one
that measured how long a template's run of leading literals was. All three
scores agree with the gateway on rows 5-10 and disagree with it on the row that
was filed against them, which is why those rows are in the suite and why a score
of that shape is not what the gateway computes.

Row 4 is the only row in the suite where declaration order decides anything.
