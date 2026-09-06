"""Tables, their retention and the order they are swept in (spec section 1)."""


class Schema:
    def __init__(self, tables, errors):
        self._tables = list(tables)
        self._retain = {t["name"]: t.get("retain_days") for t in tables}
        known = set(self._retain)

        self._parent = {}
        for table in self._tables:
            parent = table.get("parent")
            if parent is not None and parent not in known:   # 1.4
                errors.append({"code": "UNKNOWN_PARENT", "detail": table["name"]})
                parent = None
            self._parent[table["name"]] = parent

    def parent_of(self, name):
        return self._parent.get(name)

    def retention_of(self, name):
        return self._retain.get(name)

    def _depth(self, name, seen=()):
        parent = self._parent.get(name)
        if parent is None or parent in seen:
            return 0
        return 1 + self._depth(parent, seen + (name,))

    def sweep_order(self):
        """1.3: a table further from the root is swept first, so a child is
        always gone before its parent is considered. Ties go by name."""
        return sorted(self._tables,
                      key=lambda table: (-self._depth(table["name"]), table["name"]))
