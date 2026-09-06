"""Assembling the report (spec sections 1, 5)."""
import json

from .compare import CHANGED, Comparison
from .paths import Ignores

MISSING = "MISSING"
UNMANAGED = "UNMANAGED"


def index(resources, code, errors):
    """1.2: the first resource with a given id stands; a later one is an error."""
    seen = {}
    for resource in resources:
        rid = resource["id"]
        if rid in seen:
            errors.append({"code": code, "detail": rid})
            continue
        seen[rid] = resource["body"]
    return seen


def detect(capture):
    ignores = Ignores(capture.get("ignore") or [])
    errors = []
    declared = index(capture.get("declared") or [], "DUPLICATE_DECLARED", errors)
    live = index(capture.get("live") or [], "DUPLICATE_LIVE", errors)

    drift = []
    counts = {}

    def record(resource, path, kind, values=None):
        entry = {"resource": resource, "path": path, "kind": kind}
        if values is not None:
            entry["declared"], entry["live"] = values      # 5.2 only on CHANGED
        drift.append(entry)
        counts[kind] = counts.get(kind, 0) + 1              # 5.3

    for rid in sorted(set(declared) | set(live)):           # 5.1 by resource id
        if rid not in live:
            record(rid, "", MISSING)                        # 1.3, 4.4
            continue
        if rid not in declared:
            record(rid, "", UNMANAGED)                      # 1.4, 4.4
            continue
        comparison = Comparison(ignores)
        comparison.walk(declared[rid], live[rid])           # 1.5
        for finding in sorted(comparison.findings,
                              key=lambda item: item["path"]):   # 5.1 by path
            values = None
            if finding["kind"] == CHANGED:
                values = (finding["declared"], finding["live"])
            record(rid, finding["path"], finding["kind"], values)

    return {"drift": drift, "counts": counts, "errors": errors}


def detect_text(text):
    return detect(json.loads(text))
