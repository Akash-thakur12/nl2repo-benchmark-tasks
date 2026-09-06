"""Comparing one declared body against one live body (spec section 3)."""
from .paths import child, index_segment

CHANGED = "CHANGED"
ADDED = "ADDED"
REMOVED = "REMOVED"


def json_kind(value):
    """The JSON type, with bool separated from number so 3.5 can be honoured."""
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


class Comparison:
    def __init__(self, ignores):
        self._ignores = ignores
        self.findings = []

    def _changed(self, path, declared, live):
        self.findings.append({"path": path, "kind": CHANGED,
                              "declared": declared, "live": live})

    def _absent(self, path, kind):
        if not self._ignores.covers(path):
            self.findings.append({"path": path, "kind": kind})

    def walk(self, declared, live, path=""):
        if self._ignores.covers(path):
            return
        if json_kind(declared) != json_kind(live):      # 3.4 the descent stops
            self._changed(path, declared, live)
            return
        if isinstance(declared, dict):
            self._objects(declared, live, path)
            return
        if isinstance(declared, list):
            self._lists(declared, live, path)
            return
        if declared != live:                            # 3.5 type-strict already
            self._changed(path, declared, live)

    def _objects(self, declared, live, path):
        for key in sorted(set(declared) | set(live)):   # 3.1
            here = child(path, key)
            if key not in live:                         # 3.2, 3.6
                self._absent(here, REMOVED)
            elif key not in declared:
                self._absent(here, ADDED)
            else:
                self.walk(declared[key], live[key], here)

    def _lists(self, declared, live, path):
        shared = min(len(declared), len(live))          # 3.3
        for position in range(shared):
            self.walk(declared[position], live[position],
                      child(path, index_segment(position)))
        for position in range(shared, len(live)):
            self._absent(child(path, index_segment(position)), ADDED)
        for position in range(shared, len(declared)):
            self._absent(child(path, index_segment(position)), REMOVED)
