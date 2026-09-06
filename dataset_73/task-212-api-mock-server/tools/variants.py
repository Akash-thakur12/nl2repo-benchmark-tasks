#!/usr/bin/env python3
"""A parameterised mock engine, used to prove the corpora discriminate.

`Engine()` with no flags reproduces tests/reference_mock.py exactly. Every flag
turns one decision into a plausible wrong reading of it. tools/check_shortcuts.py
uses the flags for near-misses of the written specification; tools/check_crux.py
uses them for the four decisions the specification deliberately does not spell
out.

This module does not ship in the task image.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_mock as ref  # noqa: E402

MODULUS = ref.COUNTER_MODULUS


class Engine(object):
    def __init__(self,
                 # --- reading the specification carelessly (check_shortcuts)
                 method_before_path=False, no_allow_header=False,
                 allow_unsorted=False, path_case_insensitive=False,
                 strip_trailing_slash=False, body_before_query=False,
                 loose_int=False, loose_bool_query=False, bool_is_int=False,
                 number_is_string=False, unknown_before_declared=False,
                 unknown_in_insertion_order=False, unknown_always_allowed=False,
                 fixture_when_any=False, times_shared=False,
                 times_counts_failures=False, missing_fixture_is_500=False,
                 # --- crux B: route precedence
                 precedence="leftmost",
                 # --- crux E: the request counter
                 order="counter", report_in_handling_order=False,
                 # --- crux I: the contract in force
                 reloads="counter", matched_base="live", tallies="per_contract",
                 # --- crux G: HEAD
                 head="implicit"):
        self.method_before_path = method_before_path
        self.no_allow_header = no_allow_header
        self.allow_unsorted = allow_unsorted
        self.path_case_insensitive = path_case_insensitive
        self.strip_trailing_slash = strip_trailing_slash
        self.body_before_query = body_before_query
        self.loose_int = loose_int
        self.loose_bool_query = loose_bool_query
        self.bool_is_int = bool_is_int
        self.number_is_string = number_is_string
        self.unknown_before_declared = unknown_before_declared
        self.unknown_in_insertion_order = unknown_in_insertion_order
        self.unknown_always_allowed = unknown_always_allowed
        self.fixture_when_any = fixture_when_any
        self.times_shared = times_shared
        self.times_counts_failures = times_counts_failures
        self.missing_fixture_is_500 = missing_fixture_is_500
        self.precedence = precedence
        self.order = order
        self.report_in_handling_order = report_in_handling_order
        self.reloads = reloads
        self.matched_base = matched_base
        self.tallies = tallies
        self.head = head

    # ---------------------------------------------------------- small pieces
    def value_is(self, value, kind):
        if kind == "int" and self.bool_is_int:
            return isinstance(value, int)
        if kind == "string" and self.number_is_string:
            return isinstance(value, (str, int, float)) and not isinstance(value, bool)
        return ref.value_is(value, kind)

    def parse_query(self, raw, kind):
        if kind == "int" and self.loose_int:
            try:
                int(raw, 10)
                return True
            except ValueError:
                return False
        if kind == "bool" and self.loose_bool_query:
            return raw.lower() in ("true", "false", "1", "0", "yes", "no")
        return ref.parse_query_value(raw, kind)

    def check_query(self, route, request):
        for field in route.get("query") or []:
            name = field["name"]
            supplied = request.get("query") or {}
            if name not in supplied:
                if field.get("required"):
                    return ref.problem(400, {"error": "missing_query", "name": name})
                continue
            if not self.parse_query(supplied[name], field["type"]):
                return ref.problem(400, {"error": "bad_query", "name": name})
        return None

    def check_body(self, route, request):
        schema = route.get("body") or []
        supplied = request.get("body") or {}
        declared = {f["name"] for f in schema}

        def unknowns():
            if self.unknown_always_allowed or route.get("allow_unknown"):
                return None
            names = list(supplied) if self.unknown_in_insertion_order else sorted(supplied)
            for name in names:
                if name not in declared:
                    return ref.problem(400, {"error": "unknown_field", "name": name})
            return None

        if self.unknown_before_declared:
            failure = unknowns()
            if failure is not None:
                return failure
        for field in schema:
            name = field["name"]
            if name not in supplied:
                if field.get("required"):
                    return ref.problem(400, {"error": "missing_field", "name": name})
                continue
            if not self.value_is(supplied[name], field["type"]):
                return ref.problem(400, {"error": "bad_field", "name": name})
        if self.unknown_before_declared:
            return None
        return unknowns()

    def answers(self, route_method, request_method):
        if route_method == request_method:
            return True
        if self.head == "literal":
            return False
        return request_method == "HEAD" and route_method == "GET"

    def allow(self, candidates):
        ordered = []
        for item in candidates:
            if item[1]["method"] not in ordered:
                ordered.append(item[1]["method"])
        if self.head != "literal" and "GET" in ordered and "HEAD" not in ordered:
            ordered.append("HEAD")
        if self.allow_unsorted:
            return ", ".join(ordered)
        return ", ".join(sorted(set(ordered)))

    def winner(self, candidates):
        def literals(item):
            return sum(1 for part in ref.segments(item[1]["path"])
                       if not ref.is_parameter(part))
        if self.precedence == "first":
            return candidates[0]
        if self.precedence == "most_literals":
            return min(candidates, key=lambda item: (-literals(item), item[0]))
        if self.precedence == "most_params":
            return min(candidates, key=lambda item: (literals(item), item[0]))
        if self.precedence == "longest_prefix":
            def run(item):
                n = 0
                for part in ref.segments(item[1]["path"]):
                    if ref.is_parameter(part):
                        break
                    n += 1
                return n
            return min(candidates, key=lambda item: (-run(item), item[0]))
        return ref.best_candidate(candidates)

    # ------------------------------------------------------------ the engine
    def handle(self, request, routes, tally_for):
        method = request["method"]
        candidates = []
        for index, route in enumerate(routes):
            template, path = route["path"], request["path"]
            if self.strip_trailing_slash:
                template = template.rstrip("/") or "/"
                path = path.rstrip("/") or "/"
            if self.path_case_insensitive:
                template = template.lower()
                path = path.lower()
            params = ref.match_path(template, path)
            if params is None:
                continue
            if self.method_before_path and route["method"] != method:
                continue
            candidates.append((index, route, params))

        if not candidates:
            return ref.problem(404, {"error": "no_route"}), None

        exact = [item for item in candidates if item[1]["method"] == method]
        answering = exact or [item for item in candidates
                              if self.answers(item[1]["method"], method)]
        if not answering:
            headers = {} if self.no_allow_header else {"allow": self.allow(candidates)}
            return ref.problem(405, {"error": "method_not_allowed"}, headers), None

        index, route, params = self.winner(answering)

        if self.body_before_query:
            failure = self.check_body(route, request) or self.check_query(route, request)
        else:
            failure = self.check_query(route, request) or self.check_body(route, request)
        if failure is not None:
            if self.times_counts_failures:
                served = tally_for(index)
                served[0] = served.get(0, 0) + 1
            return failure, index

        served = tally_for(index)
        chosen = None
        for position, fixture in enumerate(route["fixtures"]):
            limit = fixture.get("times")
            if limit is not None and served.get(position, 0) >= limit:
                continue
            when = fixture.get("when") or {}
            if self.fixture_when_any:
                fits = (not when) or any(params.get(k) == v for k, v in when.items())
            else:
                fits = all(params.get(k) == v for k, v in when.items())
            if fits:
                served[position] = served.get(position, 0) + 1
                chosen = fixture
                break

        if chosen is None:
            status = 500 if self.missing_fixture_is_500 else 404
            return ref.problem(status, {"error": "no_fixture"}), index

        return ref.problem(chosen["status"], chosen["body"]), index

    def __call__(self, capture):
        requests = capture.get("requests") or []
        count = len(requests)
        responses = [None] * count
        matched = [None] * count
        if not count:
            return {"responses": responses, "matched": matched}

        first = ref.run_start([request["seq"] for request in requests])
        base_routes = capture.get("routes") or []
        entries = capture.get("reloads") or []
        plan = [(0, base_routes)]
        for entry in entries:
            plan.append((ref.position(entry["at"], first), entry.get("routes") or []))

        if self.order == "file":
            order = list(range(count))
        elif self.order == "raw_seq":
            order = sorted(range(count), key=lambda slot: requests[slot]["seq"])
        else:
            order = ref.handling_order(requests, first)

        shared = {}
        buckets = {}

        def tally_for(generation, index):
            if self.times_shared:
                return shared
            key = index if self.tallies == "carried" else (generation, index)
            return buckets.setdefault(key, {})

        for step, slot in enumerate(order):
            request = requests[slot]
            if self.reloads == "ignore":
                generation, routes = 0, base_routes
            elif self.reloads == "last":
                generation, routes = len(plan) - 1, plan[-1][1]
            elif self.reloads == "file_position":
                generation, routes = ref.contract_at(plan, slot)
            elif self.reloads == "step_position":
                generation, routes = ref.contract_at(plan, step)
            else:
                generation, routes = ref.contract_at(
                    plan, ref.position(request["seq"], first))

            answer, index = self.handle(
                request, routes, lambda i, g=generation: tally_for(g, i))

            if index is not None and self.matched_base == "initial":
                index = self.reindex(routes, index, base_routes)

            if request["method"] == "HEAD" and self.head != "literal":
                if self.head == "implicit":
                    answer = dict(answer, body=None)
                elif self.head == "suppress_2xx" and 200 <= answer["status"] < 300:
                    answer = dict(answer, body=None)

            responses[slot] = answer
            matched[slot] = index

        if self.report_in_handling_order:
            responses = [responses[slot] for slot in order]
            matched = [matched[slot] for slot in order]

        return {"responses": responses, "matched": matched}

    @staticmethod
    def reindex(routes, index, base_routes):
        """The wrong default that reports every match against the first contract."""
        route = routes[index]
        for position, candidate in enumerate(base_routes):
            if (candidate["method"] == route["method"]
                    and candidate["path"] == route["path"]):
                return position
        return index


def corpora():
    """(samples, recordings, held-out) as lists of pathlib.Path."""
    return (sorted((ROOT / "environment" / "samples").glob("*.capture")),
            sorted((ROOT / "environment" / "reference").glob("*.capture")),
            sorted((ROOT / "tests" / "captures").glob("*.capture")))
