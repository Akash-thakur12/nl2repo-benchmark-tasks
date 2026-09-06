"""Path templates and route precedence (spec sections 1, 2)."""

OPEN, CLOSE = "{", "}"


def segments(path):
    """1.3: the leading slash is not a segment; a trailing one leaves an empty."""
    return path[1:].split("/") if path.startswith("/") else path.split("/")


def is_parameter(segment):
    return segment.startswith(OPEN) and segment.endswith(CLOSE)


def capture(template, path):
    """1.2, 1.3: equal length, literals equal case-sensitively, a brace segment
    takes whatever one segment is there. Returns the parameters, or None."""
    wanted = segments(template)
    given = segments(path)
    if len(wanted) != len(given):
        return None
    params = {}
    for expected, actual in zip(wanted, given):
        if is_parameter(expected):
            params[expected[1:-1]] = actual
        elif expected != actual:
            return None
    return params


def literal_mask(template):
    """docs/gateway-routing.md: the template's shape, one entry per segment,
    1 for a literal and 0 for a parameter.

    The gateway's choice between two candidates depends only on their shapes.
    Candidates always have the same number of segments - they all matched the
    same request - so two masks are the same length and compare position by
    position from the left. The leftmost position where one has a literal and
    the other a parameter decides it, whatever the rest of the templates look
    like; that is why a count of literals, or a count weighted the other way,
    or the length of a leading run of literals, all get rows 1 to 3 of the
    routing table wrong.
    """
    return tuple(0 if is_parameter(part) else 1 for part in segments(template))


def precedence_key(item):
    """Sort key that puts the winning candidate first: shapes compared from the
    left, then declaration order between two templates of identical shape."""
    index, route = item[0], item[1]
    return (tuple(-bit for bit in literal_mask(route["path"])), index)


def answers(route_method, request_method):
    """A route answers its own method. A GET route also answers HEAD, which is
    a GET whose response carries no body (RFC 9110, and reference/r06)."""
    if route_method == request_method:
        return True
    return request_method == "HEAD" and route_method == "GET"


class Router:
    def __init__(self, routes):
        self._routes = list(routes)

    def candidates(self, path):
        """2.1: every template that matches, whatever its method."""
        found = []
        for index, route in enumerate(self._routes):
            params = capture(route["path"], path)
            if params is not None:
                found.append((index, route, params))
        return found

    @staticmethod
    def answering(candidates, method):
        """2.3: a route declared for the method itself is preferred; only when
        none is declared does an implicit answer stand in (reference/r07)."""
        exact = [item for item in candidates if item[1]["method"] == method]
        if exact:
            return exact
        return [item for item in candidates
                if answers(item[1]["method"], method)]

    @staticmethod
    def best(candidates):
        """2.4: the candidate that beats every other, per gateway-routing.md."""
        return min(candidates, key=precedence_key)

    @staticmethod
    def allow_header(candidates):
        """2.3: the methods the candidates answer, sorted. A GET candidate also
        answers HEAD, so HEAD belongs in the list; a declared HEAD route does
        not put it there twice (reference/r07)."""
        methods = {item[1]["method"] for item in candidates}
        if "GET" in methods:
            methods.add("HEAD")
        return ", ".join(sorted(methods))
