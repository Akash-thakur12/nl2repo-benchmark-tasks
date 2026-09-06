"""Reference model for the mock server.

Section numbers in comments refer to docs/mock-spec.md; where that document
defers to another artifact the comment names it instead (docs/gateway-routing.md
for route precedence, reference/recorded.json for the counter, reloads and
HEAD). This is the authority for expected output; nothing is hardcoded.
"""
import json
import re

INT_RE = re.compile(r"^-?[0-9]+$")
COUNTER_MODULUS = 65536          # capture-format.md: a 16-bit request counter


# --------------------------------------------------------------- path templates
def segments(path):
    """1.3: the leading slash is not a segment, a trailing one leaves an empty."""
    return path[1:].split("/") if path.startswith("/") else path.split("/")


def is_parameter(part):
    return part.startswith("{") and part.endswith("}")


def match_path(template, path):
    """1.2, 1.3: same length, literals equal, a brace segment takes anything.

    Returns the captured parameters, or None when the template does not match.
    """
    wanted = segments(template)
    actual = segments(path)
    if len(wanted) != len(actual):
        return None
    captured = {}
    for expected, given in zip(wanted, actual):
        if is_parameter(expected):
            captured[expected[1:-1]] = given
            continue
        if expected != given:
            return None
    return captured


def literal_mask(template):
    """docs/gateway-routing.md: 1 for a literal segment, 0 for a parameter.

    Two candidates always have the same segment count, so their masks compare
    position by position from the left. The first position where one has a
    literal and the other a parameter decides; identical masks fall through to
    declaration order.
    """
    return tuple(0 if is_parameter(part) else 1 for part in segments(template))


def precedence_key(item):
    index, route = item[0], item[1]
    return (tuple(-bit for bit in literal_mask(route["path"])), index)


def best_candidate(candidates):
    """docs/gateway-routing.md: the candidate that beats every other."""
    return min(candidates, key=precedence_key)


def answers(route_method, request_method):
    """reference/r06-r08: a GET route also answers HEAD (RFC 9110)."""
    if route_method == request_method:
        return True
    return request_method == "HEAD" and route_method == "GET"


def allow_methods(candidates):
    """2.3: the methods the candidates answer, which includes HEAD whenever a
    GET candidate exists (reference/r07)."""
    methods = {item[1]["method"] for item in candidates}
    if "GET" in methods:
        methods.add("HEAD")
    return ", ".join(sorted(methods))


# ------------------------------------------------------------------ validation
def parse_query_value(raw, kind):
    """3.3: strict parsing, no coercion beyond what is written here."""
    if kind == "string":
        return True
    if kind == "int":
        return bool(INT_RE.match(raw))
    if kind == "bool":
        return raw in ("true", "false")
    raise ValueError("unknown query type %r" % (kind,))


def value_is(value, kind):
    """4.3: strict types, so a bool is never an int and a number never a string."""
    if kind == "string":
        return isinstance(value, str)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "object":
        return isinstance(value, dict)
    raise ValueError("unknown body type %r" % (kind,))


def problem(status, body, headers=None):
    return {"status": status, "body": body, "headers": headers or {}}


def check_query(route, request):
    for field in route.get("query") or []:                  # 3.4 schema order
        name = field["name"]
        supplied = (request.get("query") or {})
        if name not in supplied:
            if field.get("required"):
                return problem(400, {"error": "missing_query", "name": name})  # 3.2
            continue
        if not parse_query_value(supplied[name], field["type"]):
            return problem(400, {"error": "bad_query", "name": name})          # 3.3
    return None                                             # 3.5 extras ignored


def check_body(route, request):
    schema = route.get("body") or []
    supplied = request.get("body") or {}
    for field in schema:                                    # 4.4 schema order
        name = field["name"]
        if name not in supplied:
            if field.get("required"):
                return problem(400, {"error": "missing_field", "name": name})  # 4.2
            continue
        if not value_is(supplied[name], field["type"]):
            return problem(400, {"error": "bad_field", "name": name})          # 4.3
    if route.get("allow_unknown"):
        return None
    declared = {field["name"] for field in schema}
    for name in sorted(supplied):                           # 4.5 after the rest
        if name not in declared:
            return problem(400, {"error": "unknown_field", "name": name})
    return None


def choose_fixture(route, params, served):
    for index, fixture in enumerate(route["fixtures"]):      # 5.1, 5.2
        limit = fixture.get("times")
        if limit is not None and served.get(index, 0) >= limit:
            continue                                         # 5.4
        when = fixture.get("when") or {}
        if all(params.get(key) == value for key, value in when.items()):
            served[index] = served.get(index, 0) + 1
            return fixture
    return None                                              # 5.3


# ---------------------------------------------------------------- the counter
def run_start(seqs):
    """capture-format.md: the run is unbroken, so exactly one value in it has no
    predecessor. That value is where the run began, wrap or no wrap."""
    present = set(seqs)
    starts = [value for value in present
              if (value - 1) % COUNTER_MODULUS not in present]
    return min(starts) if len(starts) != 1 else starts[0]


def position(seq, first):
    """How far into the run a counter value sits, unwrapped."""
    return (seq - first) % COUNTER_MODULUS


def handling_order(requests, first):
    """7.1: the mock handled the requests in counter order, whatever order the
    collector workers wrote them in."""
    return sorted(range(len(requests)),
                  key=lambda i: position(requests[i]["seq"], first))


def contract_plan(capture, first):
    """reference/r03-r05: the top-level routes, then one entry per reload, each
    with the run position from which it is in force."""
    plan = [(0, capture.get("routes") or [])]
    for reload_entry in capture.get("reloads") or []:
        plan.append((position(reload_entry["at"], first),
                     reload_entry.get("routes") or []))
    return plan


def contract_at(plan, pos):
    """reference/r03-r05: the newest contract whose reload sits at or before this
    request's own place in the run. Returns (generation, routes)."""
    generation = 0
    for candidate in range(1, len(plan)):
        if plan[candidate][0] <= pos:
            generation = candidate
    return generation, plan[generation][1]


# ------------------------------------------------------------------- the mock
def handle(request, routes, tallies, generation):
    method = request["method"]

    candidates = []
    for index, route in enumerate(routes):                   # 2.1
        params = match_path(route["path"], request["path"])
        if params is not None:
            candidates.append((index, route, params))

    if not candidates:                                       # 2.2
        return problem(404, {"error": "no_route"}), None

    exact = [item for item in candidates if item[1]["method"] == method]
    answering = exact or [item for item in candidates
                          if answers(item[1]["method"], method)]
    if not answering:                                        # 2.3
        return (problem(405, {"error": "method_not_allowed"},
                        {"allow": allow_methods(candidates)}), None)

    index, route, params = best_candidate(answering)

    failure = check_query(route, request)
    if failure is None:
        failure = check_body(route, request)                 # 4.4 query first
    if failure is not None:
        return failure, index

    served = tallies.setdefault((generation, index), {})
    fixture = choose_fixture(route, params, served)
    if fixture is None:                                      # 5.3
        return problem(404, {"error": "no_fixture"}), index

    return problem(fixture["status"], fixture["body"]), index


def serve(capture):
    requests = capture.get("requests") or []
    responses = [None] * len(requests)
    matched = [None] * len(requests)
    if not requests:
        return {"responses": responses, "matched": matched}

    first = run_start([request["seq"] for request in requests])
    plan = contract_plan(capture, first)
    tallies = {}

    for slot in handling_order(requests, first):             # 7.1
        request = requests[slot]
        generation, routes = contract_at(
            plan, position(request["seq"], first))
        answer, index = handle(request, routes, tallies, generation)
        if request["method"] == "HEAD":
            answer = dict(answer, body=None)   # reference/r06-r08: never a body
        responses[slot] = answer                             # 7.2 file order
        matched[slot] = index

    return {"responses": responses, "matched": matched}


def serve_text(text):
    return serve(json.loads(text))
