#!/usr/bin/env python3
"""Regenerate the sample and held-out sweep corpora, and samples/expected.json.

  samples/         Six captures from a sweep with nothing in its way: one table
                   with no parent and no children, every row either comfortably
                   inside its retention or comfortably past it, no holds, no
                   batch limit and no dry run. Almost every plausible reading of
                   the specification reproduces expected.json here.

  tests/sweeps/    Held-out captures covering the rest: the expiry boundary,
                   tables that are never swept, parent and child ordering, a
                   parent blocked by a surviving child, holds that are active
                   and holds that have lapsed, the batch limit and what it
                   leaves pending, dry runs, and a parent that does not exist.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_retention  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sweeps"


def table(name, retain_days=None, parent=None):
    record = {"name": name}
    if retain_days is not None:
        record["retain_days"] = retain_days
    if parent is not None:
        record["parent"] = parent
    return record


def row(table_name, row_id, created, parent_id=None):
    record = {"table": table_name, "id": row_id, "created": created}
    if parent_id is not None:
        record["parent_id"] = parent_id
    return record


def hold(table_name, ids, until=None):
    record = {"table": table_name, "ids": list(ids)}
    if until is not None:
        record["until"] = until
    return record


def sweep(tables, rows, now=100, batch_limit=None, dry_run=None, holds=None):
    payload = {"now": now, "tables": tables, "rows": rows}
    if batch_limit is not None:
        payload["batch_limit"] = batch_limit
    if dry_run is not None:
        payload["dry_run"] = dry_run
    if holds is not None:
        payload["holds"] = holds
    return payload


ORDERS = [table("orders", 30)]


# ------------------------------------------------------------ benign samples
def benign():
    # A single table with no parent and no children, every row either well
    # inside its retention or well past it, no holds, no batch limit and no dry
    # run. The expiry boundary, cascade ordering, holds, the limit and the dry
    # run flag are all settled by the held-out corpus.
    s = {}
    s["s01"] = sweep(ORDERS, [row("orders", 1, 10)])
    s["s02"] = sweep(ORDERS, [row("orders", 1, 95)])
    s["s03"] = sweep(ORDERS, [row("orders", 1, 10), row("orders", 2, 95)])
    # Rows are already in id order and the two tables are already declared in
    # name order, so neither sorting rule can show itself here.
    s["s04"] = sweep(ORDERS, [row("orders", 1, 10), row("orders", 2, 10),
                              row("orders", 3, 10)])
    s["s05"] = sweep([table("events", 10), table("orders", 30)],
                     [row("events", 1, 10), row("orders", 1, 10)])
    s["s06"] = sweep(ORDERS, [])
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- the expiry boundary is inclusive (2.1) -----------------------------
    s["h01"] = sweep(ORDERS, [row("orders", 1, 70)])
    s["h02"] = sweep(ORDERS, [row("orders", 1, 71)])
    s["h03"] = sweep(ORDERS, [row("orders", 1, 69), row("orders", 2, 70),
                              row("orders", 3, 71)])

    # -- a table with no retention is never swept (1.2) ---------------------
    s["h04"] = sweep([table("audit")], [row("audit", 1, 0)])
    s["h05"] = sweep([table("orders", 30), table("audit")],
                     [row("orders", 1, 10), row("audit", 1, 0)])

    # -- children are swept before parents (1.3) ----------------------------
    parent_child = [table("orders", 30), table("order_lines", 30, parent="orders")]
    s["h06"] = sweep(parent_child,
                     [row("orders", 1, 10), row("order_lines", 5, 10, parent_id=1)])

    # -- and the order does not depend on the name (1.3) --------------------
    s["h07"] = sweep([table("zzz", 30), table("aaa", 30, parent="zzz")],
                     [row("zzz", 1, 10), row("aaa", 5, 10, parent_id=1)])

    # -- three levels deep ---------------------------------------------------
    s["h08"] = sweep([table("a", 30), table("b", 30, parent="a"),
                      table("c", 30, parent="b")],
                     [row("a", 1, 10), row("b", 2, 10, parent_id=1),
                      row("c", 3, 10, parent_id=2)])

    # -- sibling tables sort by name (1.3) ----------------------------------
    s["h09"] = sweep([table("zebra", 30), table("alpha", 30)],
                     [row("zebra", 1, 10), row("alpha", 1, 10)])

    # -- a surviving child blocks its parent (4.2, 4.3) ---------------------
    s["h10"] = sweep(parent_child,
                     [row("orders", 1, 10), row("order_lines", 5, 95, parent_id=1)])

    s["h11"] = sweep(parent_child,
                     [row("orders", 1, 10), row("order_lines", 5, 10, parent_id=1),
                      row("order_lines", 6, 95, parent_id=1)])

    # -- a held child blocks its parent (3.3, 4.2) --------------------------
    s["h12"] = sweep(parent_child,
                     [row("orders", 1, 10), row("order_lines", 5, 10, parent_id=1)],
                     holds=[hold("order_lines", [5])])

    # -- a child of another parent does not block (4.1) ---------------------
    s["h13"] = sweep(parent_child,
                     [row("orders", 1, 10), row("orders", 2, 10),
                      row("order_lines", 5, 95, parent_id=2)])

    # -- a parent_id naming nothing blocks nothing (4.4) --------------------
    s["h14"] = sweep(parent_child,
                     [row("orders", 1, 10), row("order_lines", 5, 95, parent_id=99)])

    # -- holds, active and lapsed (3.1-3.4) ---------------------------------
    s["h15"] = sweep(ORDERS, [row("orders", 1, 10)], holds=[hold("orders", [1])])
    s["h16"] = sweep(ORDERS, [row("orders", 1, 10)],
                     holds=[hold("orders", [1], until=100)])
    s["h17"] = sweep(ORDERS, [row("orders", 1, 10)],
                     holds=[hold("orders", [1], until=99)])
    s["h18"] = sweep(ORDERS, [row("orders", 1, 10)],
                     holds=[hold("orders", [1], until=99), hold("orders", [1])])
    s["h19"] = sweep(ORDERS, [row("orders", 1, 10), row("orders", 2, 10)],
                     holds=[hold("orders", [2])])

    # -- a hold on a row that is not expired shows nothing (2.2, 3.3) -------
    s["h20"] = sweep(ORDERS, [row("orders", 1, 95)], holds=[hold("orders", [1])])

    # -- a hold naming another table does not protect (3.1) -----------------
    s["h21"] = sweep([table("orders", 30), table("events", 30)],
                     [row("orders", 1, 10), row("events", 1, 10)],
                     holds=[hold("events", [1])])

    # -- the batch limit (5.1-5.4) ------------------------------------------
    three = [row("orders", 1, 10), row("orders", 2, 10), row("orders", 3, 10)]
    s["h22"] = sweep(ORDERS, three, batch_limit=2)
    s["h23"] = sweep(ORDERS, three, batch_limit=0)
    s["h24"] = sweep(ORDERS, three, batch_limit=3)
    s["h25"] = sweep(ORDERS, three, batch_limit=9)

    # -- the limit still lets a held or blocked row be reported (5.4) -------
    s["h26"] = sweep(ORDERS, three, batch_limit=1, holds=[hold("orders", [3])])
    s["h27"] = sweep(parent_child,
                     [row("orders", 1, 10), row("orders", 2, 10),
                      row("order_lines", 5, 95, parent_id=2)],
                     batch_limit=0)

    # -- the limit stopping a child blocks its parent (4.2, 5.3) ------------
    s["h28"] = sweep(parent_child,
                     [row("orders", 1, 10), row("order_lines", 5, 10, parent_id=1)],
                     batch_limit=0)

    # -- a dry run decides everything the same way (6.1, 6.2) ---------------
    s["h29"] = sweep(ORDERS, three, dry_run=True)
    s["h30"] = sweep(ORDERS, three, batch_limit=2, dry_run=True)
    s["h31"] = sweep(parent_child,
                     [row("orders", 1, 10), row("order_lines", 5, 95, parent_id=1)],
                     dry_run=True)

    # -- a parent that does not exist (1.4) ---------------------------------
    s["h32"] = sweep([table("orders", 30, parent="widgets")],
                     [row("orders", 1, 10)])
    s["h33"] = sweep([table("a", 30, parent="ghost"), table("b", 30, parent="a")],
                     [row("a", 1, 10), row("b", 2, 10, parent_id=1)])

    # -- rows are considered by id, whatever order the dump was in (5.2) ----
    s["h34"] = sweep(ORDERS, [row("orders", 3, 10), row("orders", 1, 10),
                              row("orders", 2, 10)], batch_limit=2)

    # -- everything at once ---------------------------------------------------
    s["h35"] = sweep([table("orders", 30), table("order_lines", 30, parent="orders"),
                      table("audit"), table("ghosts", 30, parent="nowhere")],
                     [row("orders", 1, 10), row("orders", 2, 10), row("orders", 3, 10),
                      row("order_lines", 5, 10, parent_id=1),
                      row("order_lines", 6, 95, parent_id=2),
                      row("audit", 1, 0), row("ghosts", 1, 10)],
                     batch_limit=3, holds=[hold("orders", [3], until=200)])
    return s


def write(target, sweeps):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(sweeps.items()):
        (target / (name + ".sweep")).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".sweep")).read_text(encoding="utf-8")
        expected[name] = reference_retention.sweep_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
