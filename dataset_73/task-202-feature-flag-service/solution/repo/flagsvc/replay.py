"""Scenario parsing and the record loop."""
import json

from .registry import Registry


def parse(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def replay(text):
    registry = Registry()
    evaluations = []
    for record in parse(text):
        op = record["op"]
        if op == "end":
            break
        if op in ("define", "update"):          # 6.1, 6.2: no caching in between
            registry.put(record["flag"])
        elif op == "delete":
            registry.drop(record["flag"])
        elif op == "evaluate":
            result = registry.evaluate(record["flag"], record["user"])
            evaluations.append({
                "flag": record["flag"],
                "user": record["user"]["key"],
                "variant": result.variant,
                "reason": result.reason,
            })
        else:
            raise ValueError("unknown op {!r}".format(op))
    return {"evaluations": evaluations, "flags": registry.keys}
