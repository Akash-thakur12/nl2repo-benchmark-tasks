"""Reference model for drift detection, following docs/drift-spec.md literally.

Section numbers in comments refer to that document. This is the authority for
expected output; nothing is hardcoded.
"""
import json

MISSING = "MISSING"
UNMANAGED = "UNMANAGED"
CHANGED = "CHANGED"
ADDED = "ADDED"
REMOVED = "REMOVED"


def join(path, segment):
    """2.2-2.4: a leading dot is never emitted."""
    if segment.startswith("["):
        return path + segment
    return segment if not path else path + "." + segment


def split_path(path):
    """Break a rendered path back into its segments, list indices included."""
    segments = []
    current = ""
    index = 0
    while index < len(path):
        char = path[index]
        if char == ".":
            if current:
                segments.append(current)
            current = ""
            index += 1
            continue
        if char == "[":
            if current:
                segments.append(current)
                current = ""
            close = path.index("]", index)
            segments.append(path[index:close + 1])
            index = close + 1
            continue
        current += char
        index += 1
    if current:
        segments.append(current)
    return segments


def rule_matches(rule, path):
    """4.1, 4.2: a * matches exactly one segment, key or index."""
    rule_parts = split_path(rule)
    path_parts = split_path(path)
    if len(rule_parts) != len(path_parts):
        return False
    for expected, actual in zip(rule_parts, path_parts):
        if expected in ("*", "[*]"):
            continue
        if expected != actual:
            return False
    return True


def ignored(rules, path):
    """4.3: a match suppresses that path and everything beneath it."""
    if not path:
        return False
    parts = split_path(path)
    prefix = ""
    for segment in parts:
        prefix = join(prefix, segment)
        if any(rule_matches(rule, prefix) for rule in rules):
            return True
    return False


def json_kind(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return "null"


def compare(declared, live, path, rules, out):
    if ignored(rules, path):
        return
    if json_kind(declared) != json_kind(live):              # 3.4
        out.append({"path": path, "kind": CHANGED,
                    "declared": declared, "live": live})
        return
    if isinstance(declared, dict):
        for key in sorted(set(declared) | set(live)):       # 3.1
            child = join(path, key)
            if key not in live:
                if not ignored(rules, child):
                    out.append({"path": child, "kind": REMOVED})   # 3.2
                continue
            if key not in declared:
                if not ignored(rules, child):
                    out.append({"path": child, "kind": ADDED})
                continue
            compare(declared[key], live[key], child, rules, out)
        return
    if isinstance(declared, list):
        shared = min(len(declared), len(live))              # 3.3
        for index in range(shared):
            compare(declared[index], live[index],
                    join(path, "[" + str(index) + "]"), rules, out)
        for index in range(shared, len(live)):
            child = join(path, "[" + str(index) + "]")
            if not ignored(rules, child):
                out.append({"path": child, "kind": ADDED})
        for index in range(shared, len(declared)):
            child = join(path, "[" + str(index) + "]")
            if not ignored(rules, child):
                out.append({"path": child, "kind": REMOVED})
        return
    if declared != live:                                    # 3.5
        out.append({"path": path, "kind": CHANGED,
                    "declared": declared, "live": live})


def index_resources(resources, code, errors):
    """1.2: the first of a repeated id stands."""
    seen = {}
    for resource in resources:
        rid = resource["id"]
        if rid in seen:
            errors.append({"code": code, "detail": rid})
            continue
        seen[rid] = resource["body"]
    return seen


def detect(capture):
    rules = list(capture.get("ignore") or [])
    errors = []
    declared = index_resources(capture.get("declared") or [],
                               "DUPLICATE_DECLARED", errors)
    live = index_resources(capture.get("live") or [], "DUPLICATE_LIVE", errors)

    findings = []
    for rid in sorted(set(declared) | set(live)):           # 5.1
        if rid not in live:
            findings.append({"resource": rid, "path": "", "kind": MISSING})    # 1.3
            continue
        if rid not in declared:
            findings.append({"resource": rid, "path": "", "kind": UNMANAGED})  # 1.4
            continue
        found = []
        compare(declared[rid], live[rid], "", rules, found)                    # 1.5
        for entry in sorted(found, key=lambda item: item["path"]):
            findings.append(dict(entry, resource=rid))

    counts = {}
    for finding in findings:
        counts[finding["kind"]] = counts.get(finding["kind"], 0) + 1           # 5.3

    drift = []
    for finding in findings:
        record = {"resource": finding["resource"], "path": finding["path"],
                  "kind": finding["kind"]}
        if finding["kind"] == CHANGED:                                         # 5.2
            record["declared"] = finding["declared"]
            record["live"] = finding["live"]
        drift.append(record)

    return {"drift": drift, "counts": counts, "errors": errors}


def detect_text(text):
    return detect(json.loads(text))
