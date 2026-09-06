"""The request counter, the contract in force, and the request loop.

Sections 5, 6 and 7 of docs/mock-spec.md, plus the two things that document
leaves to the recordings in reference/: how a reload lines up with the counter,
and what a HEAD gets back.
"""
import json

from .routing import Router
from .validation import check_body, check_query

COUNTER_MODULUS = 65536      # capture-format.md: the counter is 16-bit


class FixtureSet:
    """The fixtures of one route, and how many times each has answered."""

    def __init__(self, fixtures):
        self._fixtures = list(fixtures)
        self._served = {}

    def choose(self, params):
        for position, fixture in enumerate(self._fixtures):    # 5.1 in order
            limit = fixture.get("times")
            if limit is not None and self._served.get(position, 0) >= limit:
                continue                                       # 5.4 used up
            conditions = fixture.get("when") or {}
            if all(params.get(key) == value
                   for key, value in conditions.items()):      # 5.1 every one
                self._served[position] = self._served.get(position, 0) + 1
                return fixture                                 # 5.2 the first
        return None                                            # 5.3


class Contract:
    """One route list, with the fixture tallies that belong to it.

    A reload swaps the list outright rather than merging, so the tallies of the
    contract it replaced do not carry over: a fixture with `times: 1` in the new
    list has not answered anything yet (reference/r05).
    """

    def __init__(self, routes):
        self.routes = list(routes)
        self.router = Router(self.routes)
        self._fixtures = {index: FixtureSet(route["fixtures"])
                          for index, route in enumerate(self.routes)}

    def fixtures(self, index):
        # one tally per route, never shared, so exhausting a fixture on one path
        # leaves every other path untouched
        return self._fixtures[index]


class Timeline:
    """The captured run of the request counter, and the contracts along it.

    The counter wraps, so a raw `seq` is not a position: 0 can come after 65535
    within one run. The run is unbroken, which makes exactly one of its values
    have no predecessor in the capture, and that value is where the run began.
    Everything else is measured from there.
    """

    def __init__(self, capture):
        requests = capture.get("requests") or []
        self.first = self._start([request["seq"] for request in requests])
        self._marks = [(0, Contract(capture.get("routes") or []))]
        for entry in capture.get("reloads") or []:
            self._marks.append((self.position(entry["at"]),
                                Contract(entry.get("routes") or [])))

    @staticmethod
    def _start(seqs):
        present = set(seqs)
        if not present:
            return 0
        heads = [value for value in present
                 if (value - 1) % COUNTER_MODULUS not in present]
        return min(heads) if len(heads) != 1 else heads[0]

    def position(self, seq):
        """How far into the run a counter value sits, with the wrap undone."""
        return (seq - self.first) % COUNTER_MODULUS

    def order(self, requests):
        """7.1: the order the mock handled them in, which is counter order and
        not the order the collector's workers wrote them out in."""
        return sorted(range(len(requests)),
                      key=lambda slot: self.position(requests[slot]["seq"]))

    def contract(self, pos):
        """The newest contract whose reload sits at or before this request's own
        place in the run - not the contract at the end of the file, and not the
        one the loop happens to have reached (reference/r03, r04)."""
        current = self._marks[0][1]
        for at, contract in self._marks[1:]:
            if at <= pos:
                current = contract
        return current


def response(status, body, headers=None):
    return {"status": status, "body": body, "headers": headers or {}}


def answer(request, contract):
    """The response and the matched route index for one request."""
    method = request["method"]
    candidates = contract.router.candidates(request["path"])
    if not candidates:                                         # 2.2
        return response(404, {"error": "no_route"}), None

    allowed = Router.answering(candidates, method)
    if not allowed:                                            # 2.3
        return (response(405, {"error": "method_not_allowed"},
                         {"allow": Router.allow_header(candidates)}), None)

    index, route, params = Router.best(allowed)                # 2.4

    refused = check_query(route.get("query"), request.get("query") or {})
    if refused is None:                                        # 4.4 query first
        refused = check_body(route.get("body"), request.get("body") or {},
                             route.get("allow_unknown"))
    if refused is not None:
        # a refused request never reaches a fixture, so it cannot use one up
        return refused, index

    fixture = contract.fixtures(index).choose(params)
    if fixture is None:                                        # 5.3
        return response(404, {"error": "no_fixture"}), index

    return response(fixture["status"], fixture["body"]), index


def serve(capture):
    requests = capture.get("requests") or []
    timeline = Timeline(capture)

    responses = [None] * len(requests)
    matched = [None] * len(requests)

    for slot in timeline.order(requests):                      # 7.1
        request = requests[slot]
        pos = timeline.position(request["seq"])
        reply, index = answer(request, timeline.contract(pos))
        if request["method"] == "HEAD":
            # a HEAD response never has a body, whatever the status
            # (reference/r06 for a 200, r08 for a 404 and a 400)
            reply = dict(reply, body=None)
        responses[slot] = reply                                # 7.2 file order
        matched[slot] = index

    return {"responses": responses, "matched": matched}


def serve_text(text):
    return serve(json.loads(text))
