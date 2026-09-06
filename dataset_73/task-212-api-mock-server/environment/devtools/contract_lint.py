#!/usr/bin/env python3
"""contract_lint - warn about routes that another route will swallow.

    python3 contract_lint.py path/to/*.capture

Platform team convenience script. We run it in the contract repo's pre-commit
hook so nobody lands a route that can never be reached. It is a heuristic and
it is not the mock: it does not answer requests, it only looks at the shapes of
the templates. If it disagrees with the mock, the mock is right.

Example output:

    s07.capture
      route 1 GET /acme/{a}/{b}/{c} is shadowed by
        route 0 GET /{tenant}/settings/theme/mode (more literal segments)
      2 requests, 1 route reachable, 1 shadowed

Exit status is 1 if anything was reported, so the hook can block the commit.
"""
import json
import sys


def segments(path):
    return path[1:].split("/") if path.startswith("/") else path.split("/")


def is_parameter(part):
    return part.startswith("{") and part.endswith("}")


def specificity(path):
    """How specific a template is: the number of segments it pins down.

    A template with more literal segments constrains more of the path, so it is
    the one the router reaches for first.
    """
    return sum(1 for part in segments(path) if not is_parameter(part))


def overlap(first, second):
    """True when some request path would match both templates."""
    left, right = segments(first), segments(second)
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if is_parameter(a) or is_parameter(b):
            continue
        if a != b:
            return False
    return True


def shadowed(routes):
    """Pairs (loser, winner) where the loser can never be reached.

    Between two overlapping templates the more specific one wins; equally
    specific templates are separated by declaration order, earliest first.
    """
    found = []
    for i, low in enumerate(routes):
        for j, high in enumerate(routes):
            if i == j or low["method"] != high["method"]:
                continue
            if not overlap(low["path"], high["path"]):
                continue
            beaten = (specificity(high["path"]) > specificity(low["path"])
                      or (specificity(high["path"]) == specificity(low["path"])
                          and j < i))
            if beaten:
                found.append((i, j))
                break
    return found


def reason(routes, loser, winner):
    if specificity(routes[winner]["path"]) > specificity(routes[loser]["path"]):
        return "more literal segments"
    return "declared earlier"


def lint(name, capture):
    routes = capture.get("routes") or []
    # The replay tool walks capture["requests"] straight through in file order,
    # so the counts below line up one-for-one with the report it writes.
    requests = capture.get("requests") or []
    pairs = shadowed(routes)

    print(name)
    for loser, winner in pairs:
        print("  route %d %s %s is shadowed by" % (
            loser, routes[loser]["method"], routes[loser]["path"]))
        print("    route %d %s %s (%s)" % (
            winner, routes[winner]["method"], routes[winner]["path"],
            reason(routes, loser, winner)))
    print("  %d requests, %d route%s reachable, %d shadowed" % (
        len(requests), len(routes) - len(pairs),
        "" if len(routes) - len(pairs) == 1 else "s", len(pairs)))
    return len(pairs)


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: contract_lint.py <capture> [<capture> ...]\n")
        return 2
    total = 0
    for path in argv[1:]:
        with open(path, encoding="utf-8") as handle:
            total += lint(path, json.load(handle))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
