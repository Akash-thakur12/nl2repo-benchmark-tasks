"""Reference model for the retention sweep, following docs/retention-spec.md
literally. Section numbers in comments refer to that document. This is the
authority for expected output; nothing is hardcoded.
"""
import json


def sweep_order(tables, errors):
    """1.3, 1.4: children before parents, then by name."""
    known = {table["name"] for table in tables}
    parent_of = {}
    for table in tables:
        parent = table.get("parent")
        if parent is not None and parent not in known:
            errors.append({"code": "UNKNOWN_PARENT", "detail": table["name"]})
            parent = None
        parent_of[table["name"]] = parent

    def depth(name, seen=()):
        parent = parent_of.get(name)
        if parent is None or parent in seen:
            return 0
        return 1 + depth(parent, seen + (name,))

    # a deeper table is further from the root, so it is swept first
    return sorted(tables, key=lambda table: (-depth(table["name"]), table["name"]))


def active_holds(holds, now):
    """3.1-3.4: a hold with no until never lapses, one dated before now has."""
    held = set()
    for hold in holds or []:
        until = hold.get("until")
        if until is not None and until < now:
            continue                                        # 3.2 lapsed
        for row_id in hold.get("ids") or []:
            held.add((hold["table"], row_id))
    return held


def sweep(capture):
    now = capture["now"]
    limit = capture.get("batch_limit")
    dry_run = bool(capture.get("dry_run"))
    tables = capture.get("tables") or []
    rows = capture.get("rows") or []

    errors = []
    ordered_tables = sweep_order(tables, errors)
    retain = {table["name"]: table.get("retain_days") for table in tables}
    parent_of = {table["name"]: table.get("parent") for table in tables}

    by_table = {}
    for row in rows:
        by_table.setdefault(row["table"], []).append(row)
    for table_rows in by_table.values():
        table_rows.sort(key=lambda row: row["id"])          # 5.2

    holds = active_holds(capture.get("holds"), now)

    # a row survives until the sweep decides otherwise
    surviving = {(row["table"], row["id"]) for row in rows}
    children_of = {}
    for row in rows:
        parent_table = parent_of.get(row["table"])
        if parent_table is None:
            continue
        parent_id = row.get("parent_id")
        if parent_id is None:
            continue                                        # 4.4
        children_of.setdefault((parent_table, parent_id), []).append(
            (row["table"], row["id"]))

    deleted, held, blocked = [], [], []
    pending = 0

    for table in ordered_tables:
        name = table["name"]
        days = retain.get(name)
        if days is None:                                    # 1.2 never swept
            continue
        for row in by_table.get(name, []):
            if now - row["created"] < days:                 # 2.1, 2.2
                continue
            key = (name, row["id"])
            if key in holds:                                # 3.3
                held.append({"table": name, "id": row["id"]})
                continue
            alive = [child for child in children_of.get(key, [])
                     if child in surviving]
            if alive:                                       # 4.3
                blocked.append({"table": name, "id": row["id"]})
                continue
            if limit is not None and len(deleted) >= limit:  # 5.1, 5.3, 5.4
                pending += 1
                continue
            deleted.append({"table": name, "id": row["id"]})
            surviving.discard(key)                          # 4.2

    return {"deleted": deleted, "held": held, "blocked": blocked,
            "pending": pending, "applied": not dry_run, "errors": errors}


def sweep_text(text):
    return sweep(json.loads(text))
