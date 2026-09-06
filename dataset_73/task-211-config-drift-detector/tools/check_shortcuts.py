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
import reference_drift as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "states"


def loose_equal(a, b):
    """Python's own ==, which cannot tell True from 1 or 1 from 1.0."""
    return a == b


def strict_equal(a, b):
    return a == b and ref.json_kind(a) == ref.json_kind(b)


def make_detect(equal=None, path_leading_dot=False, list_index_dotted=False,
                ignore_prefix_only=False, ignore_matches_parent=False,
                ignore_matches_deeper=False, ignore_not_inherited=False,
                ignore_hits_resources=False, star_not_index=False,
                lists_by_length=False, type_change_descends=False,
                empty_object_is_absent=False, duplicate_last_wins=False,
                duplicate_silent=False, sort_by_path_first=False,
                changed_without_values=False, swap_kinds=False,
                resources_unsorted=False, paths_unsorted=False):
    equal = equal or strict_equal

    def path_join(path, segment):
        if segment.startswith("["):
            return (path + segment) if not list_index_dotted else \
                (segment if not path else path + "." + segment)
        if path_leading_dot:
            return path + "." + segment
        return segment if not path else path + "." + segment

    def is_ignored(rules, path):
        if not path:
            return False
        parts = ref.split_path(path)
        candidates = []
        if ignore_not_inherited:
            candidates = [path]
        else:
            prefix = ""
            for segment in parts:
                prefix = path_join(prefix, segment)
                candidates.append(prefix)
        for candidate in candidates:
            for rule in rules:
                if ignore_prefix_only:
                    if candidate.startswith(rule.replace(".*", "")):
                        return True
                    continue
                rule_parts = ref.split_path(rule)
                cand_parts = ref.split_path(candidate)
                if ignore_matches_parent and len(rule_parts) == len(cand_parts) + 1 \
                        and rule_parts[-1] in ("*", "[*]") \
                        and rule_parts[:-1] == cand_parts:
                    return True
                if ignore_matches_deeper and len(cand_parts) >= len(rule_parts):
                    trimmed = cand_parts[:len(rule_parts)]
                    if all(r in ("*", "[*]") or r == a
                           for r, a in zip(rule_parts, trimmed)):
                        return True
                if len(rule_parts) != len(cand_parts):
                    continue
                matched = True
                for expected, actual in zip(rule_parts, cand_parts):
                    if expected in ("*", "[*]"):
                        if star_not_index and actual.startswith("["):
                            matched = False
                            break
                        continue
                    if expected != actual:
                        matched = False
                        break
                if matched:
                    return True
        return False

    def compare(declared, live, path, rules, out):
        if is_ignored(rules, path):
            return
        same_kind = ref.json_kind(declared) == ref.json_kind(live)
        if not same_kind:
            if not type_change_descends:
                out.append({"path": path, "kind": ref.CHANGED,
                            "declared": declared, "live": live})
                return
            # descend anyway by treating the side that is not an object as empty
            if isinstance(declared, dict) or isinstance(live, dict):
                declared = declared if isinstance(declared, dict) else {}
                live = live if isinstance(live, dict) else {}
            else:
                out.append({"path": path, "kind": ref.CHANGED,
                            "declared": declared, "live": live})
                return
        if isinstance(declared, dict) and isinstance(live, dict):
            for key in sorted(set(declared) | set(live)):
                child = path_join(path, key)
                in_declared = key in declared
                in_live = key in live
                if empty_object_is_absent:
                    if in_declared and declared[key] == {}:
                        in_declared = False
                    if in_live and live[key] == {}:
                        in_live = False
                if not in_live:
                    if not is_ignored(rules, child):
                        out.append({"path": child, "kind": ref.REMOVED})
                    continue
                if not in_declared:
                    if not is_ignored(rules, child):
                        out.append({"path": child, "kind": ref.ADDED})
                    continue
                compare(declared[key], live[key], child, rules, out)
            return
        if isinstance(declared, list) and isinstance(live, list):
            if lists_by_length:
                if len(declared) != len(live):
                    out.append({"path": path, "kind": ref.CHANGED,
                                "declared": declared, "live": live})
                    return
            shared = min(len(declared), len(live))
            for index in range(shared):
                compare(declared[index], live[index],
                        path_join(path, "[" + str(index) + "]"), rules, out)
            for index in range(shared, len(live)):
                child = path_join(path, "[" + str(index) + "]")
                if not is_ignored(rules, child):
                    out.append({"path": child, "kind": ref.ADDED})
            for index in range(shared, len(declared)):
                child = path_join(path, "[" + str(index) + "]")
                if not is_ignored(rules, child):
                    out.append({"path": child, "kind": ref.REMOVED})
            return
        if not equal(declared, live):
            out.append({"path": path, "kind": ref.CHANGED,
                        "declared": declared, "live": live})

    def index(resources, code, errors):
        seen = {}
        for resource in resources:
            rid = resource["id"]
            if rid in seen:
                if not duplicate_silent:
                    errors.append({"code": code, "detail": rid})
                if not duplicate_last_wins:
                    continue
            seen[rid] = resource["body"]
        return seen

    def do(capture):
        rules = list(capture.get("ignore") or [])
        errors = []
        declared = index(capture.get("declared") or [], "DUPLICATE_DECLARED", errors)
        live = index(capture.get("live") or [], "DUPLICATE_LIVE", errors)

        findings = []
        order = sorted(set(declared) | set(live))
        if resources_unsorted:
            order = list(declared) + [r for r in live if r not in declared]
        for rid in order:
            if ignore_hits_resources and any(r in ("*", rid) for r in rules):
                continue
            if rid not in live:
                findings.append({"resource": rid, "path": "",
                                 "kind": ref.UNMANAGED if swap_kinds else ref.MISSING})
                continue
            if rid not in declared:
                findings.append({"resource": rid, "path": "",
                                 "kind": ref.MISSING if swap_kinds else ref.UNMANAGED})
                continue
            found = []
            compare(declared[rid], live[rid], "", rules, found)
            ordered_found = found if paths_unsorted else                 sorted(found, key=lambda item: item["path"])
            for entry in ordered_found:
                findings.append(dict(entry, resource=rid))

        if sort_by_path_first:
            findings.sort(key=lambda item: (item["path"], item["resource"]))

        counts = {}
        for finding in findings:
            counts[finding["kind"]] = counts.get(finding["kind"], 0) + 1

        drift = []
        for finding in findings:
            record = {"resource": finding["resource"], "path": finding["path"],
                      "kind": finding["kind"]}
            if finding["kind"] == ref.CHANGED and not changed_without_values:
                record["declared"] = finding["declared"]
                record["live"] = finding["live"]
            drift.append(record)
        return {"drift": drift, "counts": counts, "errors": errors}
    return do


# Four near-misses are deliberately absent, because none of them can be told
# apart from the specification:
#
#   - comparing scalars without a type check. Rule 3.4 settles a difference of
#     type before the scalar comparison is ever reached, so the loose comparison
#     never sees a pair it would judge differently.
#   - treating an ignore rule as matching every path beneath it, and checking a
#     rule against the full path only. The comparison recurses, and a node whose
#     own path is ignored is never descended into, so inheritance is already
#     implied by the recursion and neither variant changes an outcome.
#   - seeding counts with a zero for every kind. That can only agree with the
#     specification on a corpus where all five kinds occur, which no benign
#     corpus can be, so it could never be evidence of anything.
SHORTCUTS = [
    ("a top-level path is rendered with a leading dot", make_detect(path_leading_dot=True)),
    ("a list index is joined with a dot", make_detect(list_index_dotted=True)),
    ("an ignore rule is treated as a string prefix", make_detect(ignore_prefix_only=True)),
    ("an ignore rule also matches the parent it names", make_detect(ignore_matches_parent=True)),
    ("an ignore rule can suppress a whole resource", make_detect(ignore_hits_resources=True)),
    ("a wildcard does not match a list index", make_detect(star_not_index=True)),
    ("lists of different length are reported whole", make_detect(lists_by_length=True)),
    ("a change of type is descended into anyway", make_detect(type_change_descends=True)),
    ("an empty object counts as an absent key", make_detect(empty_object_is_absent=True)),
    ("a duplicate id lets the later resource win", make_detect(duplicate_last_wins=True)),
    ("a duplicate id is skipped without an error", make_detect(duplicate_silent=True)),
    ("findings are ordered by path before resource", make_detect(sort_by_path_first=True)),
    ("a changed finding omits the two values", make_detect(changed_without_values=True)),
    ("missing and unmanaged are the other way round", make_detect(swap_kinds=True)),
    ("resources are reported in the order they were read", make_detect(resources_unsorted=True)),
    ("findings inside a resource are left in traversal order", make_detect(paths_unsorted=True)),
]


def main():
    sample_files = sorted(SAMPLES.glob("*.state"))
    held_files = sorted(HELD_OUT.glob("*.state"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    baseline = make_detect()
    for f in sample_files + held_files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        assert baseline(payload) == ref.detect(payload), \
            "the mutation harness does not reproduce the reference on %s" % f.stem

    for f in sample_files:
        assert ref.detect_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.detect_text(f.read_text(encoding="utf-8")) for f in held_files}

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
