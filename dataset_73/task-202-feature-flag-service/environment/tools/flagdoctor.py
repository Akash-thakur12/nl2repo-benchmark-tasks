#!/usr/bin/env python3
"""flagdoctor 2.4.1 - static linter for flag definitions.

Diagnostics track service v2 semantics (last rebuilt for v2.4, 2024-06-14).
This is a linter, not an evaluator: it never resolves a flag for a user and its
descriptions of what an evaluation *reports* have not been revised since v2.

    python3 flagdoctor.py <scenario_file> [...]
"""
import json
import sys


def _flags(records):
    """Every definition seen, keyed by flag key, most recent last."""
    seen = {}
    order = []
    for rec in records:
        if rec.get("op") in ("define", "update"):
            key = rec["flag"]["key"]
            seen.setdefault(key, []).append(rec["flag"])
            if key not in order:
                order.append(key)
        elif rec.get("op") == "delete":
            pass
    return order, seen


def _cycle(order, seen):
    graph = {k: [p["flag"] for p in defs[-1].get("prerequisites", [])]
             for k, defs in seen.items()}
    state = {}

    def walk(node, path):
        if state.get(node) == "done":
            return None
        if node in path:
            return path[path.index(node):] + [node]
        for nxt in graph.get(node, []):
            found = walk(nxt, path + [node])
            if found:
                return found
        state[node] = "done"
        return None

    for key in order:
        found = walk(key, [])
        if found:
            return found
    return None


def lint(path):
    with open(path, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    order, seen = _flags(records)
    out = []

    for key in order:
        defs = seen[key]
        salts = [d.get("salt") for d in defs]
        if len(set(salts)) > 1:
            out.append("W12: flag %r redefined with a different salt; bucket "
                       "assignments will change for all users" % key)
        for definition in defs:
            for rule in definition.get("rules", []):
                rollout = rule.get("rollout")
                if rollout is None:
                    continue
                total = sum(entry["weight"] for entry in rollout)
                if total != 10000:
                    out.append("W07: rollout weights sum to %d, not 10000 - "
                               "traffic above the total is served the last "
                               "variant" % total)
                if any(entry["weight"] == 0 for entry in rollout):
                    out.append("W03: rollout in flag %r has a zero-weight "
                               "variant, which can never be served" % key)
            for prereq in definition.get("prerequisites", []):
                if prereq["flag"] not in seen:
                    out.append("E01: flag %r requires undefined flag %r"
                               % (key, prereq["flag"]))

    cycle = _cycle(order, seen)
    if cycle:
        out.append("E03: prerequisite cycle %s; the affected evaluation "
                   "reports PREREQUISITE_FAILED" % " -> ".join(cycle))
    return out


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: flagdoctor.py <scenario_file> [...]\n")
        return 2
    worst = 0
    for path in argv[1:]:
        for line in lint(path):
            print("%s: %s" % (path, line))
            worst = max(worst, 2 if line.startswith("E") else 1)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
