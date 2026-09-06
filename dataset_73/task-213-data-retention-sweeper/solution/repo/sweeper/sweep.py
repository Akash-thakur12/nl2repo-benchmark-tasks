"""The sweep itself (spec sections 2, 4, 5, 6, 7)."""
import json

from .holds import Holds
from .schema import Schema


class Population:
    """Every row, indexed the two ways the sweep needs to look at them."""

    def __init__(self, rows, schema):
        self._by_table = {}
        for row in rows:
            self._by_table.setdefault(row["table"], []).append(row)
        for group in self._by_table.values():
            group.sort(key=lambda row: row["id"])            # 5.2

        self.surviving = {(row["table"], row["id"]) for row in rows}

        self._children = {}
        for row in rows:
            parent_table = schema.parent_of(row["table"])
            if parent_table is None:
                continue
            parent_id = row.get("parent_id")
            if parent_id is None:                            # 4.4
                continue
            self._children.setdefault((parent_table, parent_id), []).append(
                (row["table"], row["id"]))

    def of(self, table):
        return self._by_table.get(table, [])

    def has_surviving_child(self, key):
        """4.2: any child still present, for whatever reason, keeps the parent."""
        return any(child in self.surviving for child in self._children.get(key, []))

    def remove(self, key):
        self.surviving.discard(key)


def run(capture):
    now = capture["now"]
    limit = capture.get("batch_limit")
    dry_run = bool(capture.get("dry_run"))

    errors = []
    schema = Schema(capture.get("tables") or [], errors)
    population = Population(capture.get("rows") or [], schema)
    holds = Holds(capture.get("holds"), now)

    deleted, held, blocked = [], [], []
    pending = 0

    for table in schema.sweep_order():
        name = table["name"]
        retention = schema.retention_of(name)
        if retention is None:                                # 1.2 never swept
            continue
        for row in population.of(name):
            if now - row["created"] < retention:             # 2.1, 2.2
                continue
            key = (name, row["id"])

            if holds.covers(name, row["id"]):                # 3.3
                held.append({"table": name, "id": row["id"]})
                continue

            if population.has_surviving_child(key):          # 4.3
                blocked.append({"table": name, "id": row["id"]})
                continue

            # 5.1, 5.3, 5.4 the sweep keeps going past the limit so that every
            # row it could not take is counted, and 6.2 a dry run counts the same
            if limit is not None and len(deleted) >= limit:
                pending += 1
                continue

            deleted.append({"table": name, "id": row["id"]})
            population.remove(key)

    return {"deleted": deleted, "held": held, "blocked": blocked,
            "pending": pending, "applied": not dry_run,      # 6.1, 7.5
            "errors": errors}


def run_text(text):
    return run(json.loads(text))
