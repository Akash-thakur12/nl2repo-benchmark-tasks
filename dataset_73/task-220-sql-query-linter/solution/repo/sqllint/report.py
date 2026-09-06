"""Severity, suppression and the report (spec sections 5, 6, 7)."""
import json

from .rules import DEFAULT_SEVERITY, collect

SEVERITIES = ("error", "warning", "style", "off")                          # 5.2
NOQA = "noqa"


def suppressed_rules(comment):
    """Section 6. None, "all", or the set of rule names named."""
    if comment is None:
        return None
    text = comment.strip()
    if text == NOQA:                                                       # 6.1
        return "all"
    prefix = NOQA + ":"
    if text.startswith(prefix):                                            # 6.2
        return {part.strip() for part in text[len(prefix):].split(",")
                if part.strip()}
    return None


def read_severities(config):
    """5.2, 5.3."""
    severities = dict(DEFAULT_SEVERITY)
    errors = []
    for rule, severity in (config.get("rules") or {}).items():
        if rule not in DEFAULT_SEVERITY:
            errors.append({"code": "UNKNOWN_RULE", "detail": rule})
            continue
        if severity not in SEVERITIES:
            errors.append({"code": "UNKNOWN_SEVERITY", "detail": severity})
            continue
        severities[rule] = severity
    return severities, errors


def lint(text, severities):
    raw, comments = collect(text)
    violations = []
    for rule, line, column in raw:
        severity = severities[rule]
        if severity == "off":                                              # 5.2
            continue
        allowed = suppressed_rules(comments.get(line))                     # 6.4
        if allowed == "all" or (isinstance(allowed, set) and rule in allowed):
            continue                                                       # 6.5
        violations.append({"line": line, "column": column, "rule": rule,
                           "severity": severity})
    violations.sort(key=lambda item: (item["line"], item["column"],        # 7.1
                                      item["rule"]))
    counts = {"error": 0, "warning": 0, "style": 0}
    for item in violations:
        counts[item["severity"]] += 1                                      # 7.3
    return violations, counts


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("capture must begin with a config record")
    severities, errors = read_severities(records[0])

    queries = []
    totals = {"error": 0, "warning": 0, "style": 0}
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] != "query":
            raise ValueError("unknown op %r" % (record["op"],))
        violations, counts = lint(record["sql"], severities)
        queries.append({"name": record["name"], "violations": violations,
                        "counts": counts})
        for key in totals:
            totals[key] += counts[key]
    return {"queries": queries, "totals": totals, "errors": errors}
