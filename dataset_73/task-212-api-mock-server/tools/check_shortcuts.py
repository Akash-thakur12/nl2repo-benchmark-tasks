#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss of a rule docs/mock-spec.md states in
so many words. For each one this asserts that it still reproduces
environment/samples/expected.json exactly, and that at least one held-out
capture catches it.

The four decisions the specification deliberately does not spell out have their
own proof in tools/check_crux.py.

This script does not ship in the task image.
"""
import json
import sys

from variants import Engine, ROOT, corpora, ref

SAMPLES = ROOT / "environment" / "samples"

SHORTCUTS = [
    ("the method is filtered before the path, so a mismatch is a 404", Engine(method_before_path=True)),
    ("the 405 carries no allow header", Engine(no_allow_header=True)),
    ("the allow header keeps declaration order", Engine(allow_unsorted=True)),
    ("the first matching route wins, whatever its shape", Engine(precedence="first")),
    ("the route with the most parameters wins", Engine(precedence="most_params")),
    ("path literals are matched case-insensitively", Engine(path_case_insensitive=True)),
    ("a trailing slash is stripped before matching", Engine(strip_trailing_slash=True)),
    ("the body is validated before the query", Engine(body_before_query=True)),
    ("an int query parameter is parsed with int()", Engine(loose_int=True)),
    ("a bool query parameter accepts yes, no, 1 and 0", Engine(loose_bool_query=True)),
    ("a bool counts as an int in the body", Engine(bool_is_int=True)),
    ("a number counts as a string in the body", Engine(number_is_string=True)),
    ("unknown fields are rejected before the declared ones are checked", Engine(unknown_before_declared=True)),
    ("unknown fields are reported in insertion order", Engine(unknown_in_insertion_order=True)),
    ("unknown fields are always allowed", Engine(unknown_always_allowed=True)),
    ("a fixture matches when any of its conditions does", Engine(fixture_when_any=True)),
    ("fixture exhaustion is shared across routes", Engine(times_shared=True)),
    ("a rejected request still consumes a fixture", Engine(times_counts_failures=True)),
    ("no matching fixture gives a 500", Engine(missing_fixture_is_500=True)),
]


def main():
    sample_files, recorded_files, held_files = corpora()
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    baseline = Engine()
    for path in sample_files + recorded_files + held_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert baseline(payload) == ref.serve(payload), \
            "the mutation harness does not reproduce the reference on %s" % path.stem

    for path in sample_files:
        assert ref.serve_text(path.read_text(encoding="utf-8")) == expected[path.stem], \
            "reference disagrees with expected.json on %s" % path.stem

    truth = {p.stem: ref.serve_text(p.read_text(encoding="utf-8")) for p in held_files}

    bad, uncaught, rows = [], [], []
    for label, engine in SHORTCUTS:
        ok = True
        for path in sample_files:
            try:
                if engine(json.loads(path.read_text(encoding="utf-8"))) != expected[path.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for path in held_files:
            try:
                if engine(json.loads(path.read_text(encoding="utf-8"))) != truth[path.stem]:
                    caught.append(path.stem)
            except Exception:
                caught.append(path.stem)
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
        for label in bad:
            print("  -", label)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out capture:")
        for label in uncaught:
            print("  -", label)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
