#!/usr/bin/env python3
"""Regenerate every capture corpus, samples/expected.json and reference/recorded.json.

  environment/samples/    Six captures from a contract with nothing tricky in
                    it: one route per path, no two templates overlapping, every
                    request matching a route and its method, no query or body
                    schema at all, one fixture per route with no `when` and no
                    `times`, GET and POST only, no reload, and a request counter
                    that ascends in file order. Almost every plausible reading
                    of the specification reproduces expected.json here.

  environment/reference/  Eight captures recorded from the live mock together
                    with the report it produced, recorded.json. These are the
                    local oracle: they pin the request counter (r01, r02), the
                    contract in force at a request's counter value (r03-r05)
                    and HEAD (r06-r08). Reproducing them is success criterion 7.

  tests/captures/   Held-out captures covering everything: route precedence,
                    method mismatches and the allow header, trailing slashes,
                    query and body validation in schema order, strict types,
                    unknown fields, fixture selection and exhaustion, the
                    counter and its wrap, reloads, and HEAD.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_mock  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
RECORDINGS = ROOT / "environment" / "reference"
HELD_OUT = ROOT / "tests" / "captures"

REQUEST_KEYS = ("method", "path", "seq", "query", "body")


def route(method, path, fixtures, query=None, body=None, allow_unknown=None):
    record = {"method": method, "path": path, "fixtures": fixtures}
    if query is not None:
        record["query"] = query
    if body is not None:
        record["body"] = body
    if allow_unknown is not None:
        record["allow_unknown"] = allow_unknown
    return record


def fixture(status, body, when=None, times=None):
    record = {"status": status, "body": body}
    if when is not None:
        record["when"] = when
    if times is not None:
        record["times"] = times
    return record


def field(name, kind, required=False):
    return {"name": name, "type": kind, "required": required}


def request(method, path, query=None, body=None, seq=None):
    record = {"method": method, "path": path}
    if seq is not None:
        record["seq"] = seq
    if query is not None:
        record["query"] = query
    if body is not None:
        record["body"] = body
    return record


def reload(at, routes):
    return {"at": at, "routes": routes}


def capture(routes, requests, reloads=None, base=1000):
    """Number the requests. A request without an explicit `seq` takes the next
    counter value, so file order equals handling order unless a capture says
    otherwise by giving every request its own `seq`."""
    counter = base
    numbered = []
    for record in requests:
        record = dict(record)
        if "seq" not in record:
            record["seq"] = counter
            counter += 1
        numbered.append({key: record[key] for key in REQUEST_KEYS
                         if key in record})
    payload = {"routes": routes}
    if reloads is not None:
        payload["reloads"] = reloads
    payload["requests"] = numbered
    return payload


OK = [fixture(200, {"ok": True})]


# ------------------------------------------------------------ benign samples
def benign():
    # One route per path, no two templates able to match the same request, every
    # request hitting a route and its method, no query or body schema anywhere,
    # exactly one fixture per route with neither a `when` nor a `times`, no
    # reload, no HEAD, and a counter that ascends in file order. Precedence,
    # the allow header, validation order, strict types, fixture exhaustion, the
    # counter, reloads and HEAD are all settled by the held-out corpus and by
    # the recordings in environment/reference.
    s = {}

    s["s01"] = capture([route("GET", "/health", OK)],
                       [request("GET", "/health")], base=1024)

    s["s02"] = capture([route("GET", "/users/{id}", [fixture(200, {"name": "ada"})])],
                       [request("GET", "/users/1"), request("GET", "/users/2")],
                       base=2048)

    s["s03"] = capture([route("GET", "/a", [fixture(200, {"which": "a"})]),
                        route("GET", "/b", [fixture(200, {"which": "b"})])],
                       [request("GET", "/a"), request("GET", "/b")], base=3072)

    s["s04"] = capture([route("POST", "/users", [fixture(201, {"created": True})])],
                       [request("POST", "/users")], base=4096)

    s["s05"] = capture([route("GET", "/orders/{id}/lines/{line}",
                              [fixture(200, {"line": 1})])],
                       [request("GET", "/orders/7/lines/2")], base=5120)

    s["s06"] = capture([route("GET", "/health", OK)],
                       [request("GET", "/health"), request("GET", "/health"),
                        request("GET", "/health")], base=6144)
    return s


# ----------------------------------------------------- the shipped recordings
def recordings():
    r = {}

    # r01: the collector wrote the two requests in the wrong order. The mock
    # handled 4101 first, so the `times: 1` fixture answered /jobs/a.
    r["r01"] = capture(
        [route("GET", "/jobs/{id}",
               [fixture(200, {"slot": "first"}, times=1),
                fixture(200, {"slot": "second"})])],
        [request("GET", "/jobs/b", seq=4102),
         request("GET", "/jobs/a", seq=4101)])

    # r02: one run across the wrap, written out of order.
    r["r02"] = capture(
        [route("GET", "/ping", [fixture(200, {"n": "early"}, times=2),
                                fixture(200, {"n": "late"})])],
        [request("GET", "/ping", seq=0), request("GET", "/ping", seq=65534),
         request("GET", "/ping", seq=1), request("GET", "/ping", seq=65535)])

    # r03: the contract was replaced mid-recording. /old exists only before,
    # /new only after.
    r["r03"] = capture(
        [route("GET", "/old", [fixture(200, {"era": "old"})]),
         route("GET", "/both", [fixture(200, {"era": "before"})])],
        [request("GET", "/old"), request("GET", "/new"),
         request("GET", "/old"), request("GET", "/new")],
        reloads=[reload(502, [route("GET", "/both",
                                    [fixture(200, {"era": "after"})]),
                              route("GET", "/new",
                                    [fixture(200, {"era": "new"})])])],
        base=500)

    # r04: the post-reload request was written first, and the two routes swap
    # index across the reload.
    r["r04"] = capture(
        [route("GET", "/alpha", [fixture(200, {"gen": "a-old"})]),
         route("GET", "/beta", [fixture(200, {"gen": "b-old"})])],
        [request("GET", "/beta", seq=8004), request("GET", "/beta", seq=8002),
         request("GET", "/alpha", seq=8003)],
        reloads=[reload(8003, [route("GET", "/beta",
                                     [fixture(200, {"gen": "b-new"})]),
                               route("GET", "/alpha",
                                     [fixture(200, {"gen": "a-new"})])])])

    # r05: the `times: 1` fixture was used up, then the reload brought a fresh
    # route list.
    token = [fixture(201, {"issued": 1}, times=1),
             fixture(429, {"error": "rate"})]
    r["r05"] = capture(
        [route("GET", "/token", token)],
        [request("GET", "/token"), request("GET", "/token"),
         request("GET", "/token"), request("GET", "/token")],
        reloads=[reload(302, [route("GET", "/token", token)])],
        base=300)

    # r06: a HEAD against a route declared only for GET.
    r["r06"] = capture(
        [route("GET", "/report", [fixture(200, {"page": 1}, times=1),
                                  fixture(200, {"page": 2})])],
        [request("HEAD", "/report"), request("GET", "/report")], base=10)

    # r07: an explicitly declared HEAD route, and three allow headers.
    r["r07"] = capture(
        [route("GET", "/a/{x}", [fixture(200, {"r": "get-a"})]),
         route("HEAD", "/a/{x}", [fixture(200, {"r": "head-a"})]),
         route("GET", "/b", [fixture(200, {"r": "get-b"})]),
         route("PUT", "/b", [fixture(200, {"r": "put-b"})]),
         route("POST", "/c", [fixture(200, {"r": "post-c"})]),
         route("PUT", "/c", [fixture(200, {"r": "put-c"})])],
        [request("HEAD", "/a/1"), request("POST", "/a/1"),
         request("POST", "/b"), request("GET", "/c")], base=700)

    # r08: HEAD when the mock refuses - no route, a bad query, a missing
    # required query parameter and no matching fixture.
    r["r08"] = capture(
        [route("GET", "/search", [fixture(200, {"hits": 0})],
               query=[field("q", "int", True)]),
         route("GET", "/item/{id}",
               [fixture(200, {"ok": True}, when={"id": "1"})])],
        [request("HEAD", "/missing"),
         request("HEAD", "/search", query={"q": "abc"}),
         request("HEAD", "/search"),
         request("HEAD", "/item/9")], base=900)

    return r


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- no route at all (2.2) ----------------------------------------------
    s["h01"] = capture([route("GET", "/a", OK)], [request("GET", "/b")])
    s["h02"] = capture([], [request("GET", "/a")])
    s["h03"] = capture([route("GET", "/a/b", OK)], [request("GET", "/a")])

    # -- the method does not match, and the allow header (2.3) --------------
    s["h04"] = capture([route("GET", "/a", OK)], [request("POST", "/a")])
    s["h05"] = capture([route("GET", "/a", OK), route("PUT", "/a", OK)],
                       [request("POST", "/a")])
    s["h06"] = capture([route("PUT", "/a", OK), route("GET", "/a", OK),
                        route("DELETE", "/a", OK)],
                       [request("POST", "/a")])

    # -- a literal beats a parameter, and ties go to the first (2.4) --------
    s["h07"] = capture([route("GET", "/users/{id}", [fixture(200, {"by": "param"})]),
                        route("GET", "/users/me", [fixture(200, {"by": "literal"})])],
                       [request("GET", "/users/me"), request("GET", "/users/1")])

    s["h08"] = capture([route("GET", "/users/me", [fixture(200, {"by": "literal"})]),
                        route("GET", "/users/{id}", [fixture(200, {"by": "param"})])],
                       [request("GET", "/users/me")])

    s["h09"] = capture([route("GET", "/{a}/{b}", [fixture(200, {"which": "first"})]),
                        route("GET", "/{x}/{y}", [fixture(200, {"which": "second"})])],
                       [request("GET", "/one/two")])

    # -- a trailing slash is a segment (1.3) --------------------------------
    s["h10"] = capture([route("GET", "/a", OK)], [request("GET", "/a/")])
    s["h11"] = capture([route("GET", "/a/", OK)], [request("GET", "/a")])
    s["h12"] = capture([route("GET", "/a/{b}", OK)], [request("GET", "/a/")])

    # -- literals are case-sensitive (1.2) ----------------------------------
    s["h13"] = capture([route("GET", "/Users", OK)], [request("GET", "/users")])

    # -- query validation, in schema order (3.1-3.5) ------------------------
    q = [field("page", "int", True), field("verbose", "bool", False)]
    s["h14"] = capture([route("GET", "/a", OK, query=q)],
                       [request("GET", "/a", query={"page": "1"})])
    s["h15"] = capture([route("GET", "/a", OK, query=q)],
                       [request("GET", "/a", query={})])
    s["h16"] = capture([route("GET", "/a", OK, query=q)],
                       [request("GET", "/a", query={"page": "1.5"})])
    s["h17"] = capture([route("GET", "/a", OK, query=q)],
                       [request("GET", "/a", query={"page": "-3"})])
    s["h18"] = capture([route("GET", "/a", OK, query=q)],
                       [request("GET", "/a", query={"page": "1", "verbose": "yes"})])
    s["h19"] = capture([route("GET", "/a", OK, query=q)],
                       [request("GET", "/a", query={"page": "x", "verbose": "yes"})])
    s["h20"] = capture([route("GET", "/a", OK, query=q)],
                       [request("GET", "/a", query={"page": "1", "extra": "z"})])

    # -- body validation, in schema order (4.1-4.4) -------------------------
    b = [field("name", "string", True), field("age", "int", False),
         field("admin", "bool", False), field("meta", "object", False)]
    s["h21"] = capture([route("POST", "/a", OK, body=b)],
                       [request("POST", "/a", body={"name": "ada"})])
    s["h22"] = capture([route("POST", "/a", OK, body=b)],
                       [request("POST", "/a", body={})])
    s["h23"] = capture([route("POST", "/a", OK, body=b)],
                       [request("POST", "/a", body={"name": 1})])
    s["h24"] = capture([route("POST", "/a", OK, body=b)],
                       [request("POST", "/a", body={"name": "ada", "age": True})])
    s["h25"] = capture([route("POST", "/a", OK, body=b)],
                       [request("POST", "/a", body={"name": "ada", "admin": 1})])
    s["h26"] = capture([route("POST", "/a", OK, body=b)],
                       [request("POST", "/a", body={"name": "ada", "meta": []})])

    # -- the query is validated before the body (4.4) -----------------------
    s["h27"] = capture([route("POST", "/a", OK, query=q, body=b)],
                       [request("POST", "/a", query={}, body={})])

    # -- unknown fields, after the declared ones, in name order (4.5) -------
    s["h28"] = capture([route("POST", "/a", OK, body=b)],
                       [request("POST", "/a", body={"name": "ada", "zzz": 1, "aaa": 2})])
    s["h29"] = capture([route("POST", "/a", OK, body=b, allow_unknown=True)],
                       [request("POST", "/a", body={"name": "ada", "zzz": 1})])
    s["h30"] = capture([route("POST", "/a", OK, body=b)],
                       [request("POST", "/a", body={"zzz": 1})])

    # -- fixtures chosen by path parameter (5.1, 5.2) -----------------------
    users = [fixture(200, {"who": "one"}, when={"id": "1"}),
             fixture(200, {"who": "two"}, when={"id": "2"}),
             fixture(404, {"error": "not_found"})]
    s["h31"] = capture([route("GET", "/users/{id}", users)],
                       [request("GET", "/users/1"), request("GET", "/users/2"),
                        request("GET", "/users/9")])

    s["h32"] = capture([route("GET", "/users/{id}",
                              [fixture(200, {"who": "one"}, when={"id": "1"})])],
                       [request("GET", "/users/9")])

    s["h33"] = capture([route("GET", "/a/{x}/{y}",
                              [fixture(200, {"hit": True}, when={"x": "1", "y": "2"}),
                               fixture(404, {"error": "no"})])],
                       [request("GET", "/a/1/2"), request("GET", "/a/1/3")])

    # -- a fixture that runs out (5.4) --------------------------------------
    s["h34"] = capture([route("GET", "/a", [fixture(201, {"first": True}, times=1),
                                            fixture(200, {"later": True})])],
                       [request("GET", "/a"), request("GET", "/a"),
                        request("GET", "/a")])

    s["h35"] = capture([route("GET", "/a", [fixture(201, {"first": True}, times=2)])],
                       [request("GET", "/a"), request("GET", "/a"),
                        request("GET", "/a")])

    # -- exhaustion is per route, not shared --------------------------------
    s["h36"] = capture([route("GET", "/a", [fixture(201, {"a": True}, times=1)]),
                        route("GET", "/b", [fixture(201, {"b": True}, times=1)])],
                       [request("GET", "/a"), request("GET", "/b"),
                        request("GET", "/a")])

    # -- a failed validation does not consume a fixture ---------------------
    s["h37"] = capture([route("GET", "/a", [fixture(200, {"ok": True}, times=1)],
                              query=[field("page", "int", True)])],
                       [request("GET", "/a", query={}), request("GET", "/a",
                                                                query={"page": "1"})])

    # -- everything at once --------------------------------------------------
    s["h38"] = capture(
        [route("GET", "/users/{id}", users, query=[field("v", "bool", False)]),
         route("GET", "/users/me", [fixture(200, {"who": "self"})]),
         route("POST", "/users", [fixture(201, {"created": True}, times=1)], body=b)],
        [request("GET", "/users/me"), request("GET", "/users/1", query={"v": "x"}),
         request("GET", "/users/2", query={"v": "true"}),
         request("POST", "/users", body={"name": "ada"}),
         request("POST", "/users", body={"name": "ada"}),
         request("DELETE", "/users/1"), request("GET", "/nope")])
    # -- int() would accept these; the specification does not (3.3) --------
    s["h39"] = capture([route("GET", "/a", OK, query=[field("page", "int", True)])],
                       [request("GET", "/a", query={"page": "+1"}),
                        request("GET", "/a", query={"page": " 1"}),
                        request("GET", "/a", query={"page": "1_0"})])

    # == route precedence, segment by segment from the left ==================
    # h40: three literals lose to one, because the leftmost segment decides.
    s["h40"] = capture(
        [route("GET", "/{org}/config/db/host", [fixture(200, {"win": 0})]),
         route("GET", "/acme/{a}/{b}/{c}", [fixture(200, {"win": 1})])],
        [request("GET", "/acme/config/db/host"),
         request("GET", "/globex/config/db/host")])

    # h41: equal literal counts, so a count cannot decide it.
    s["h41"] = capture(
        [route("GET", "/blob/{b}/meta/{k}", [fixture(200, {"win": 0})]),
         route("GET", "/blob/cold/{a}/{b}", [fixture(200, {"win": 1})])],
        [request("GET", "/blob/cold/meta/z"),
         request("GET", "/blob/warm/meta/z")])

    # h42: equal literal prefixes, so a prefix length cannot decide it either.
    s["h42"] = capture(
        [route("GET", "/api/{c}/{d}/end", [fixture(200, {"win": 0})]),
         route("GET", "/api/{a}/edge/{b}", [fixture(200, {"win": 1})])],
        [request("GET", "/api/q/edge/end"),
         request("GET", "/api/q/rim/end")])

    # h43: identical shapes fall through to declaration order.
    s["h43"] = capture(
        [route("GET", "/{a}/{b}/keep", [fixture(200, {"win": 0})]),
         route("GET", "/{x}/{y}/keep", [fixture(200, {"win": 1})])],
        [request("GET", "/m/n/keep")])

    # h44: three overlapping templates.
    s["h44"] = capture(
        [route("GET", "/{a}/{b}/{c}", [fixture(200, {"win": 0})]),
         route("GET", "/{a}/log/{c}", [fixture(200, {"win": 1})]),
         route("GET", "/t/{b}/{c}", [fixture(200, {"win": 2})])],
        [request("GET", "/t/log/9"), request("GET", "/u/log/9"),
         request("GET", "/u/v/9")])

    # h45: three overlapping templates whose winner is neither first nor last.
    s["h45"] = capture(
        [route("GET", "/{a}/q/{c}", [fixture(200, {"win": 0})]),
         route("GET", "/p/{b}/{c}", [fixture(200, {"win": 1})]),
         route("GET", "/{a}/{b}/{c}", [fixture(200, {"win": 2})])],
        [request("GET", "/p/q/r"), request("GET", "/z/q/r"),
         request("GET", "/z/y/r")])

    # h46: precedence is applied after the method filter, never before it.
    s["h46"] = capture(
        [route("POST", "/{a}/items/{c}", [fixture(200, {"win": 0})]),
         route("GET", "/shop/{b}/{c}", [fixture(200, {"win": 1})]),
         route("GET", "/{a}/items/{c}", [fixture(200, {"win": 2})])],
        [request("GET", "/shop/items/7"), request("GET", "/other/items/7"),
         request("POST", "/shop/items/7")])

    # == the request counter =================================================
    # h47: two requests written in the wrong order, one `times: 1` fixture.
    s["h47"] = capture(
        [route("GET", "/q/{id}", [fixture(200, {"slot": "first"}, times=1),
                                  fixture(200, {"slot": "second"})])],
        [request("GET", "/q/b", seq=4102), request("GET", "/q/a", seq=4101)])

    # h48: a shuffle where a `when` fixture and a limit interact.
    s["h48"] = capture(
        [route("GET", "/users/{id}",
               [fixture(200, {"who": "one"}, when={"id": "1"}, times=1),
                fixture(200, {"who": "fallback"})])],
        [request("GET", "/users/1", seq=205), request("GET", "/users/1", seq=203),
         request("GET", "/users/2", seq=204)])

    # h49: a run across the wrap, ascending in file order.
    s["h49"] = capture(
        [route("GET", "/ping", [fixture(200, {"n": "early"}, times=2),
                                fixture(200, {"n": "late"})])],
        [request("GET", "/ping", seq=65534), request("GET", "/ping", seq=65535),
         request("GET", "/ping", seq=0), request("GET", "/ping", seq=1)])

    # h50: a run across the wrap, shuffled, with two limited fixtures.
    s["h50"] = capture(
        [route("GET", "/ping", [fixture(201, {"n": 1}, times=1),
                                fixture(202, {"n": 2}, times=1),
                                fixture(203, {"n": 3})])],
        [request("GET", "/ping", seq=0), request("GET", "/ping", seq=65535),
         request("GET", "/ping", seq=1), request("GET", "/ping", seq=65534)])

    # h51: a shuffle with no state at all - each answer belongs to the request
    # written beside it, not to the request handled at that moment.
    s["h51"] = capture(
        [route("GET", "/a", [fixture(200, {"r": "a"})]),
         route("GET", "/b", [fixture(200, {"r": "b"})]),
         route("GET", "/c", [fixture(200, {"r": "c"})])],
        [request("GET", "/c", seq=52), request("GET", "/a", seq=50),
         request("GET", "/b", seq=51)])

    # h52: two routes running out, interleaved, written out of order.
    s["h52"] = capture(
        [route("GET", "/x", [fixture(201, {"x": 1}, times=1),
                             fixture(200, {"x": 2})]),
         route("GET", "/y", [fixture(201, {"y": 1}, times=1),
                             fixture(200, {"y": 2})])],
        [request("GET", "/x", seq=12), request("GET", "/y", seq=11),
         request("GET", "/x", seq=10), request("GET", "/y", seq=13)])

    # == the contract in force ===============================================
    # h53: a route that exists only before the reload, one only after, and one
    # that survives it at a different index.
    s["h53"] = capture(
        [route("GET", "/legacy/{id}", [fixture(200, {"era": "v1"})]),
         route("GET", "/shared", [fixture(200, {"era": "v1-shared"})])],
        [request("GET", "/shared"), request("GET", "/legacy/7"),
         request("GET", "/shared"), request("GET", "/legacy/7"),
         request("GET", "/modern/7")],
        reloads=[reload(1202, [route("GET", "/shared",
                                     [fixture(200, {"era": "v2-shared"})]),
                               route("GET", "/modern/{id}",
                                     [fixture(200, {"era": "v2"})])])],
        base=1200)

    # h54: the post-reload request is written first.
    s["h54"] = capture(
        [route("POST", "/a", [fixture(201, {"g": "a-old"})]),
         route("POST", "/b", [fixture(201, {"g": "b-old"})])],
        [request("POST", "/a", seq=9002), request("POST", "/b", seq=9000),
         request("POST", "/b", seq=9001)],
        reloads=[reload(9001, [route("POST", "/b", [fixture(201, {"g": "b-new"})]),
                               route("POST", "/a", [fixture(201, {"g": "a-new"})])])])

    # h55: the reload permutes three routes, so every index moves.
    s["h55"] = capture(
        [route("GET", "/p", [fixture(200, {"v": "p-old"})]),
         route("GET", "/q", [fixture(200, {"v": "q-old"})]),
         route("GET", "/r", [fixture(200, {"v": "r-old"})])],
        [request("GET", "/p"), request("GET", "/r"), request("GET", "/p"),
         request("GET", "/r"), request("GET", "/q")],
        reloads=[reload(55, [route("GET", "/r", [fixture(200, {"v": "r-new"})]),
                             route("GET", "/q", [fixture(200, {"v": "q-new"})]),
                             route("GET", "/p", [fixture(200, {"v": "p-new"})])])],
        base=53)

    # h56: a limited fixture used up before the reload, shuffled on top.
    limited = [fixture(201, {"n": "a"}, times=1), fixture(200, {"n": "b"})]
    s["h56"] = capture(
        [route("GET", "/k", limited)],
        [request("GET", "/k", seq=403), request("GET", "/k", seq=400),
         request("GET", "/k", seq=402), request("GET", "/k", seq=401)],
        reloads=[reload(402, [route("GET", "/k", limited)])])

    # h57: a reload inside a run that wraps.
    s["h57"] = capture(
        [route("GET", "/w", [fixture(201, {"c": "old1"}, times=1),
                             fixture(200, {"c": "old2"})])],
        [request("GET", "/w", seq=65535), request("GET", "/w", seq=0),
         request("GET", "/w", seq=65534), request("GET", "/w", seq=1)],
        reloads=[reload(0, [route("GET", "/w", [fixture(201, {"c": "new1"}, times=1),
                                                fixture(200, {"c": "new2"})])])])

    # h58: two reloads in one run, written out of order.
    s["h58"] = capture(
        [route("GET", "/s", [fixture(200, {"g": 0})])],
        [request("GET", "/s", seq=703), request("GET", "/s", seq=700),
         request("GET", "/s", seq=705), request("GET", "/s", seq=701),
         request("GET", "/s", seq=704), request("GET", "/s", seq=702)],
        reloads=[reload(702, [route("GET", "/s", [fixture(200, {"g": 1})])]),
                 reload(704, [route("GET", "/s", [fixture(200, {"g": 2})])])])

    # == HEAD ================================================================
    # h59: a HEAD answered by whichever GET route precedence picks.
    s["h59"] = capture(
        [route("GET", "/{a}/docs/{c}", [fixture(200, {"r": "param-first"})]),
         route("GET", "/site/{b}/{c}", [fixture(200, {"r": "literal-first"})])],
        [request("HEAD", "/site/docs/9"), request("GET", "/site/docs/9")])

    # h60: a HEAD uses the fixture up, so the following GET gets the next one.
    s["h60"] = capture(
        [route("GET", "/feed", [fixture(200, {"page": 1}, times=1),
                                fixture(200, {"page": 2})])],
        [request("HEAD", "/feed"), request("GET", "/feed"),
         request("HEAD", "/feed")], base=20)

    # h61: a declared HEAD route answers even when a GET route is more specific.
    s["h61"] = capture(
        [route("GET", "/res/{id}", [fixture(200, {"by": "get"})]),
         route("HEAD", "/{a}/{b}", [fixture(200, {"by": "head"})])],
        [request("HEAD", "/res/5"), request("GET", "/res/5"),
         request("HEAD", "/other/5")])

    # h62: HEAD when there is no route, and when no candidate answers it.
    s["h62"] = capture(
        [route("POST", "/only", [fixture(201, {"ok": True})])],
        [request("HEAD", "/nothing"), request("HEAD", "/only"),
         request("POST", "/only")])

    # h63: HEAD when the mock refuses the request, next to the GET that does not.
    s["h63"] = capture(
        [route("GET", "/find", [fixture(200, {"hits": 0})],
               query=[field("n", "int", True)]),
         route("GET", "/pick/{id}",
               [fixture(200, {"ok": True}, when={"id": "1"})])],
        [request("HEAD", "/find", query={"n": "zz"}), request("HEAD", "/find"),
         request("HEAD", "/pick/9"), request("GET", "/find", query={"n": "zz"})])

    # h64: the allow header lists what the candidates answer.
    s["h64"] = capture(
        [route("GET", "/m1", OK), route("PUT", "/m1", OK),
         route("POST", "/m2", OK), route("PUT", "/m2", OK),
         route("GET", "/m3", OK), route("HEAD", "/m3", OK)],
        [request("DELETE", "/m1"), request("GET", "/m2"),
         request("DELETE", "/m3"), request("HEAD", "/m2")])

    return s


def check_run(name, payload):
    """capture-format.md: one unbroken run of a 16-bit counter, with every
    reload landing inside it. A capture that breaks this is not a legal capture
    and its handling order would not be recoverable."""
    seqs = [request["seq"] for request in payload["requests"]]
    assert len(set(seqs)) == len(seqs), "%s: repeated seq" % name
    assert all(0 <= value < reference_mock.COUNTER_MODULUS for value in seqs), \
        "%s: seq outside a 16-bit counter" % name
    first = reference_mock.run_start(seqs)
    positions = sorted(reference_mock.position(value, first) for value in seqs)
    assert positions == list(range(len(seqs))), "%s: the counter run has a gap" % name
    for entry in payload.get("reloads") or []:
        at = reference_mock.position(entry["at"], first)
        assert 0 <= at < len(seqs), "%s: reload at %d is outside the run" % (
            name, entry["at"])


def write(target, captures):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(captures.items()):
        check_run(name, payload)
        (target / (name + ".capture")).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def report_for(directory, names):
    report = {}
    for name in sorted(names):
        text = (directory / (name + ".capture")).read_text(encoding="utf-8")
        report[name] = reference_mock.serve_text(text)
    return report


def main():
    samples = benign()
    recorded = recordings()
    held = held_out()

    write(SAMPLES, samples)
    write(RECORDINGS, recorded)
    write(HELD_OUT, held)

    (SAMPLES / "expected.json").write_text(
        json.dumps(report_for(SAMPLES, samples), indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    (RECORDINGS / "recorded.json").write_text(
        json.dumps(report_for(RECORDINGS, recorded), indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples    : %d" % len(samples))
    print("recordings : %d" % len(recorded))
    print("held-out   : %d" % len(held))
    print("expected.json and recorded.json written")


if __name__ == "__main__":
    main()
