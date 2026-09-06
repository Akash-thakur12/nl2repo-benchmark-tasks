#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out capture catches it.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_retention as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sweeps"


def make_sweep(expiry_exclusive=False, parents_first=False, tables_by_name=False,
               tables_in_order=False, no_retention_means_zero=False,
               holds_ignore_until=False, lapsed_hold_still_holds=False,
               hold_ignores_table=False, held_child_does_not_block=False,
               limited_child_does_not_block=False, blocked_counts_pending=False,
               held_counts_pending=False, limit_stops_sweep=False,
               dry_run_skips_limit=False, dry_run_reports_nothing=False,
               unknown_parent_silent=False, rows_in_file_order=False,
               deleted_row_still_blocks=False):

    def do(capture):
        now = capture["now"]
        limit = capture.get("batch_limit")
        dry_run = bool(capture.get("dry_run"))
        tables = capture.get("tables") or []
        rows = capture.get("rows") or []

        errors = []
        known = {t["name"] for t in tables}
        parent_of = {}
        for t in tables:
            parent = t.get("parent")
            if parent is not None and parent not in known:
                if not unknown_parent_silent:
                    errors.append({"code": "UNKNOWN_PARENT", "detail": t["name"]})
                parent = None
            parent_of[t["name"]] = parent

        def depth(name, seen=()):
            parent = parent_of.get(name)
            if parent is None or parent in seen:
                return 0
            return 1 + depth(parent, seen + (name,))

        if tables_in_order:
            ordered = list(tables)
        elif tables_by_name:
            ordered = sorted(tables, key=lambda t: t["name"])
        elif parents_first:
            ordered = sorted(tables, key=lambda t: (depth(t["name"]), t["name"]))
        else:
            ordered = sorted(tables, key=lambda t: (-depth(t["name"]), t["name"]))

        retain = {t["name"]: t.get("retain_days") for t in tables}

        by_table = {}
        for r in rows:
            by_table.setdefault(r["table"], []).append(r)
        if not rows_in_file_order:
            for group in by_table.values():
                group.sort(key=lambda r: r["id"])

        holds = set()
        for h in capture.get("holds") or []:
            until = h.get("until")
            lapsed = until is not None and until < now
            if lapsed and not (holds_ignore_until or lapsed_hold_still_holds):
                continue
            for row_id in h.get("ids") or []:
                holds.add(row_id if hold_ignores_table else (h["table"], row_id))

        def is_held(table_name, row_id):
            return (row_id in holds) if hold_ignores_table \
                else ((table_name, row_id) in holds)

        surviving = {(r["table"], r["id"]) for r in rows}
        children_of = {}
        for r in rows:
            parent_table = parent_of.get(r["table"])
            if parent_table is None:
                continue
            parent_id = r.get("parent_id")
            if parent_id is None:
                continue
            children_of.setdefault((parent_table, parent_id), []).append(
                (r["table"], r["id"], r))

        deleted, held, blocked = [], [], []
        pending = 0
        stopped = False

        for t in ordered:
            name = t["name"]
            days = retain.get(name)
            if days is None:
                if not no_retention_means_zero:
                    continue
                days = 0
            for r in by_table.get(name, []):
                if stopped and limit_stops_sweep:
                    break
                age = now - r["created"]
                expired = age > days if expiry_exclusive else age >= days
                if not expired:
                    continue
                key = (name, r["id"])
                if is_held(name, r["id"]):
                    held.append({"table": name, "id": r["id"]})
                    if held_counts_pending:
                        pending += 1
                    continue
                alive = []
                for child_table, child_id, child_row in children_of.get(key, []):
                    if (child_table, child_id) not in surviving:
                        if deleted_row_still_blocks:
                            alive.append((child_table, child_id))
                        continue
                    if held_child_does_not_block and is_held(child_table, child_id):
                        continue
                    child_days = retain.get(child_table)
                    child_expired = child_days is not None and \
                        (now - child_row["created"]) >= child_days
                    if limited_child_does_not_block and child_expired \
                            and not is_held(child_table, child_id):
                        continue
                    alive.append((child_table, child_id))
                if alive:
                    blocked.append({"table": name, "id": r["id"]})
                    if blocked_counts_pending:
                        pending += 1
                    continue
                effective_limit = limit
                if dry_run and dry_run_skips_limit:
                    effective_limit = None
                if effective_limit is not None and len(deleted) >= effective_limit:
                    pending += 1
                    stopped = True
                    continue
                deleted.append({"table": name, "id": r["id"]})
                surviving.discard(key)

        if dry_run and dry_run_reports_nothing:
            return {"deleted": [], "held": [], "blocked": [], "pending": 0,
                    "applied": False, "errors": errors}
        return {"deleted": deleted, "held": held, "blocked": blocked,
                "pending": pending, "applied": not dry_run, "errors": errors}
    return do


SHORTCUTS = [
    ("a row exactly at its retention is not yet expired", make_sweep(expiry_exclusive=True)),
    ("parents are swept before children", make_sweep(parents_first=True)),
    ("tables are swept in name order alone", make_sweep(tables_by_name=True)),
    ("tables are swept in the order they were declared", make_sweep(tables_in_order=True)),
    ("a table with no retention is swept as though it were zero", make_sweep(no_retention_means_zero=True)),
    ("a hold never lapses", make_sweep(holds_ignore_until=True)),
    ("a lapsed hold still protects", make_sweep(lapsed_hold_still_holds=True)),
    ("a hold covers the id in every table", make_sweep(hold_ignores_table=True)),
    ("a held child does not block its parent", make_sweep(held_child_does_not_block=True)),
    ("a child the limit held back does not block its parent", make_sweep(limited_child_does_not_block=True)),
    ("a blocked row counts toward pending", make_sweep(blocked_counts_pending=True)),
    ("a held row counts toward pending", make_sweep(held_counts_pending=True)),
    ("the sweep stops once the limit is reached", make_sweep(limit_stops_sweep=True)),
    ("a dry run ignores the batch limit", make_sweep(dry_run_skips_limit=True)),
    ("a dry run reports nothing at all", make_sweep(dry_run_reports_nothing=True)),
    ("an unknown parent is tolerated without an error", make_sweep(unknown_parent_silent=True)),
    ("rows are taken in the order the dump was written", make_sweep(rows_in_file_order=True)),
    ("a child that was just deleted still blocks its parent", make_sweep(deleted_row_still_blocks=True)),
]


def main():
    sample_files = sorted(SAMPLES.glob("*.sweep"))
    held_files = sorted(HELD_OUT.glob("*.sweep"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    baseline = make_sweep()
    for f in sample_files + held_files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        assert baseline(payload) == ref.sweep(payload), \
            "the mutation harness does not reproduce the reference on %s" % f.stem

    for f in sample_files:
        assert ref.sweep_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.sweep_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, fn in SHORTCUTS:
        ok = True
        for f in sample_files:
            try:
                if fn(json.loads(f.read_text(encoding="utf-8"))) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if fn(json.loads(f.read_text(encoding="utf-8"))) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out capture:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
