#!/usr/bin/env python3
"""Prove the cruxes bite, by building the wrong-default exporters and running
the real behaviour suite against each one.

Every variant below is a defensible reading of the narrowed specification, or a
line lifted straight out of one of the two non-normative artefacts that ship in
the image (`tools/explain_gap.py`, `docs/retired/impossible-travel-v1.md`). For
each one this script:

  * builds a complete, working repository whose only difference from the
    reference is that variant;
  * checks whether it still reproduces `samples/expected.json` - a variant that
    does is a genuine lure, because nothing visible contradicts it;
  * runs `tests/test_outputs.py` against it and asserts that it FAILS, and that
    the named test for that crux is among the failures.

Run it on a POSIX host (or inside the task image):

    python3 tools/check_crux.py

It ships no secrets: the wrong implementations are written out in full below and
the expected answers are computed by the same reference model the suite uses.
This script does not ship in the task image.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ENVIRONMENT = ROOT / "environment"
SAMPLES = ENVIRONMENT / "samples"
TESTS = ROOT / "tests"

# --------------------------------------------------------------------------
# The exporter, with every wrong default available as a switch. The reference
# behaviour is every switch off.
# --------------------------------------------------------------------------
EXPORTER = '''
import json, math, os, sys

V = json.loads(os.environ["VARIANT"])


def revision(entries, moment):
    """Correct as-of resolution, unless a switch says otherwise."""
    if V.get("last_entry"):
        return entries[-1]
    if V.get("first_entry"):
        return entries[0]
    ordered = sorted(entries, key=lambda e: e["from_t"])
    chosen = ordered[0]
    for entry in ordered:
        if entry["from_t"] <= moment:
            chosen = entry
        else:
            break
    return chosen


def coords_at(locations, name, moment):
    entry = locations[name]
    if isinstance(entry, list):
        if V.get("plain_only"):
            raise TypeError("locations[%r] is a list" % name)
        return revision(entry, moment)
    return entry


def limit_at(capture, earlier_t, later_t):
    policy = capture.get("speed_policy")
    if not policy or V.get("flat_limit"):
        return capture["max_speed_kmh"]
    moment = earlier_t if V.get("limit_at_earlier") else later_t
    return revision(policy, moment)["kmh"]


def distance(a, b):
    dx, dy = a["x"] - b["x"], a["y"] - b["y"]
    if V.get("round_km"):
        return round(math.sqrt(dx * dx + dy * dy))
    if V.get("ceil_km"):
        return math.ceil(math.sqrt(dx * dx + dy * dy))
    return math.isqrt(dx * dx + dy * dy)


def impossible(km, seconds, limit):
    if V.get("zero_gap_skipped") and seconds == 0:
        return False
    if V.get("inclusive_limit"):
        return km * 3600 >= limit * seconds
    return km * 3600 > limit * seconds


def export(capture):
    window = capture["dedup_window_seconds"]
    locations = capture["locations"]
    events = sorted(capture.get("events", []) or [], key=lambda e: (e["t"], e["id"]))

    accepted, duplicates, flagged, errors = [], [], [], []
    session_seen, last_success = {}, {}

    for event in events:
        name = event["location"]
        if name not in locations:
            errors.append({"code": "UNKNOWN_LOCATION", "detail": name})
            continue

        key = (event["user"], event["session"])
        previous_t = session_seen.get(key)
        if previous_t is not None:
            gap = event["t"] - previous_t
            if gap < window if V.get("dedup_exclusive") else gap <= window:
                duplicates.append(event["id"])
                continue
        if previous_t is None or not V.get("session_pinned"):
            session_seen[key] = event["t"]

        accepted.append(event["id"])
        if event["outcome"] != "success":
            continue

        seen = last_success.get(event["user"])
        was_flagged = False
        if seen is not None:
            previous_time, previous_place = seen
            km = distance(coords_at(locations, previous_place, previous_time),
                          coords_at(locations, name, event["t"]))
            seconds = event["t"] - previous_time
            if impossible(km, seconds, limit_at(capture, previous_time, event["t"])):
                was_flagged = True
                flagged.append({"id": event["id"], "user": event["user"],
                                "from": previous_place, "to": name,
                                "km": km, "seconds": seconds})
        if was_flagged and V.get("flagged_not_carried"):
            continue
        last_success[event["user"]] = (event["t"], name)

    return {"accepted": accepted, "duplicates": duplicates,
            "impossible": flagged, "errors": errors}


def main(argv):
    report = {}
    for name in sorted(os.listdir(argv[1])):
        if not name.endswith(".capture"):
            continue
        with open(os.path.join(argv[1], name), encoding="utf-8") as handle:
            report[name[:-len(".capture")]] = export(json.load(handle))
    with open(argv[2], "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''

RUN_SH = '#!/bin/sh\nset -eu\nDIR="$(cd "$(dirname "$0")" && pwd)"\n' \
         'exec python3 "$DIR/exporter.py" "$@"\n'


# --------------------------------------------------------------------------
# The wrong defaults, and the test each one must break.
# --------------------------------------------------------------------------
VARIANTS = [
    ("A: a site's current coordinates are used for every event",
     {"last_entry": True},
     "test_distance_uses_the_coordinates_in_force_at_each_event"),

    ("A: the first filed revision is used for every event",
     {"first_entry": True},
     "test_revisions_are_not_in_chronological_order"),

    ("A: locations are assumed to be plain {x, y} objects",
     {"plain_only": True},
     "test_distance_uses_the_coordinates_in_force_at_each_event"),

    ("D: the flat max_speed_kmh is used and speed_policy is ignored",
     {"flat_limit": True},
     "test_the_travel_policy_governs_when_present"),

    ("D: the policy is resolved against the earlier sign-in",
     {"limit_at_earlier": True},
     "test_the_policy_is_resolved_at_the_later_signin"),

    ("D: the policy's last filed entry is used",
     {"last_entry": True},
     "test_the_policy_is_inclusive_at_its_from_t"),

    ("B: the distance is rounded rather than floored",
     {"round_km": True},
     "test_the_distance_is_a_floored_whole_number"),

    ("B: the distance is rounded up",
     {"ceil_km": True},
     "test_the_distance_is_a_floored_whole_number"),

    ("B: the speed test is inclusive at the limit",
     {"inclusive_limit": True},
     "test_the_speed_test_is_strict_at_the_limit"),

    ("B: a zero-second gap is guarded away instead of flagged",
     {"zero_gap_skipped": True},
     "test_a_zero_second_gap_covering_ground_is_impossible"),

    ("B: the dedup window is exclusive at its boundary",
     {"dedup_exclusive": True},
     "test_dedup_window_is_inclusive_at_its_boundary"),

    ("B: a session stays pinned to its first timestamp",
     {"session_pinned": True},
     "test_an_accepted_repeat_becomes_the_new_baseline"),

    ("B: a flagged sign-in is not carried forward as the location",
     {"flagged_not_carried": True},
     "test_a_flagged_signin_still_becomes_the_previous_location"),

    ("C: tools/explain_gap.py ported wholesale (round, >=, current coordinates)",
     {"round_km": True, "inclusive_limit": True, "last_entry": True},
     "test_the_distance_is_a_floored_whole_number"),

    ("C: docs/retired/impossible-travel-v1.md implemented as written",
     {"round_km": True, "inclusive_limit": True, "last_entry": True,
      "zero_gap_skipped": True, "dedup_exclusive": True,
      "session_pinned": True, "flagged_not_carried": True, "flat_limit": True},
     "test_a_flagged_signin_still_becomes_the_previous_location"),
]

PROGRESS = re.compile(r"::([\w\[\]-]+) (PASSED|FAILED|ERROR)\b")


def build_app(root, variant):
    app = root / "app"
    shutil.copytree(SAMPLES, app / "samples")
    (app / "exporter.py").write_text(EXPORTER, encoding="utf-8")
    run = app / "run.sh"
    run.write_text(RUN_SH, encoding="utf-8")
    run.chmod(0o755)
    return app


def run_suite(app, variant):
    """Run the real suite against this exporter and return {test: status}."""
    with tempfile.TemporaryDirectory() as scratch:
        tests = pathlib.Path(scratch) / "tests"
        shutil.copytree(TESTS, tests, ignore=shutil.ignore_patterns("__pycache__"))
        env = dict(os.environ, APP_DIR=str(app), VARIANT=json.dumps(variant),
                   PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests / "test_outputs.py"),
             "-v", "--tb=no", "-p", "no:cacheprovider"],
            capture_output=True, text=True, env=env)
        return dict((name, status) for name, status in PROGRESS.findall(proc.stdout))


def main():
    if os.name != "posix":
        sys.stderr.write("run this on a POSIX host or inside the task image: "
                         "the candidate is invoked as ./run.sh\n")
        return 2

    rows, broken = [], []
    for label, variant, must_fail in VARIANTS:
        with tempfile.TemporaryDirectory() as root:
            app = build_app(pathlib.Path(root), variant)
            results = run_suite(app, variant)

        if not results:
            broken.append("%s: the suite collected nothing" % label)
            continue

        failed = sorted(k for k, v in results.items() if v != "PASSED")
        samples_ok = results.get("test_sample_report_is_reproduced") == "PASSED"
        quarter_ok = results.get("test_prior_quarter_export_is_reproduced") == "PASSED"
        rows.append((label, samples_ok, quarter_ok, len(failed), must_fail in failed))

        if not failed:
            broken.append("%s: passes the whole suite - the crux does not bite" % label)
        elif must_fail not in failed:
            broken.append("%s: %s still passes" % (label, must_fail))

    width = min(max(len(r[0]) for r in rows), 74) if rows else 20
    print("%-*s  %-8s  %-8s  %-7s  %s" % (
        width, "wrong default", "samples", "2029Q1", "failed", "its own test fails"))
    print("-" * (width + 42))
    for label, samples_ok, quarter_ok, failed, caught in rows:
        print("%-*s  %-8s  %-8s  %-7d  %s" % (
            width, label[:width],
            "repro" if samples_ok else "differs",
            "repro" if quarter_ok else "differs",
            failed, "yes" if caught else "NO"))
    print()
    print("variants                       : %d" % len(rows))
    print("still reproduce expected.json  : %d  (these are the real lures)"
          % sum(1 for r in rows if r[1]))
    print("caught by the 2029Q1 export    : %d" % sum(1 for r in rows if not r[2]))
    print("caught by the held-out suite   : %d" % sum(1 for r in rows if r[4]))

    if broken:
        print("\nPROBLEM:")
        for line in broken:
            print("  -", line)
        return 1
    print("\nOK: every wrong default fails the suite, and each fails the test "
          "written for it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
