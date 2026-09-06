#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out capture catches it.

This script does not ship in the task image.
"""
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_audit as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "captures"


# ------------------------------------------------------------ distance variants
def distance_round(a, b):
    dx, dy = a["x"] - b["x"], a["y"] - b["y"]
    return round(math.sqrt(dx * dx + dy * dy))


def distance_ceil(a, b):
    dx, dy = a["x"] - b["x"], a["y"] - b["y"]
    return math.ceil(math.sqrt(dx * dx + dy * dy))


# --------------------------------------------------------------- speed variants
def speed_inclusive(km, seconds, max_speed):
    return km * 3600 >= max_speed * seconds


def speed_float(km, seconds, max_speed):
    if seconds == 0:
        return False                      # a divide would raise, so it is skipped
    return km / (seconds / 3600) > max_speed


def speed_zero_never(km, seconds, max_speed):
    if seconds == 0:
        return False
    return km * 3600 > max_speed * seconds


# ----------------------------------------------------------------- the exporter
def make_export(distance=None, speed=None, order_by_id=False, file_order=False,
                dedup_exclusive=False, dedup_per_user=False,
                dedup_no_reset=False, duplicate_sets_location=False,
                unknown_kept=False, failure_sets_location=False,
                failure_checked=False, flag_earlier=False,
                flagged_not_previous=False, previous_is_any_event=False):
    distance = distance or ref.distance_km
    speed = speed or ref.is_impossible

    def do(capture):
        max_speed = capture["max_speed_kmh"]
        window = capture["dedup_window_seconds"]
        locations = capture["locations"]

        events = list(capture.get("events", []) or [])
        if file_order:
            pass
        elif order_by_id:
            events.sort(key=lambda e: (e["t"], e["id"]))
            events.sort(key=lambda e: e["id"])
        else:
            events.sort(key=lambda e: (e["t"], e["id"]))

        accepted, duplicates, impossible, errors = [], [], [], []
        session_seen = {}
        last_success = {}

        for event in events:
            name = event["location"]
            if name not in locations:
                errors.append({"code": "UNKNOWN_LOCATION", "detail": name})
                if not unknown_kept:
                    continue

            key = event["user"] if dedup_per_user else (event["user"], event["session"])
            previous_t = session_seen.get(key)
            gap_ok = False
            if previous_t is not None:
                gap = event["t"] - previous_t
                gap_ok = gap < window if dedup_exclusive else gap <= window
            if gap_ok:
                duplicates.append(event["id"])
                if duplicate_sets_location and name in locations:
                    last_success[event["user"]] = (event["t"], name)
                continue
            if not dedup_no_reset:
                session_seen[key] = event["t"]
            elif previous_t is None:
                session_seen[key] = event["t"]

            accepted.append(event["id"])

            success = event["outcome"] == "success"
            if not success and not failure_checked and not failure_sets_location:
                continue
            if name not in locations:
                continue

            if success or failure_checked:
                seen = last_success.get(event["user"])
                if seen is not None:
                    previous_time, previous_place = seen
                    km = distance(locations[previous_place], locations[name])
                    seconds = event["t"] - previous_time
                    if speed(km, seconds, max_speed):
                        flagged = previous_place if flag_earlier else event["id"]
                        impossible.append({
                            "id": flagged if flag_earlier else event["id"],
                            "user": event["user"], "from": previous_place,
                            "to": name, "km": km, "seconds": seconds,
                        })
                        if flagged_not_previous:
                            continue
            if success or failure_sets_location or previous_is_any_event:
                last_success[event["user"]] = (event["t"], name)

        return {"accepted": accepted, "duplicates": duplicates,
                "impossible": impossible, "errors": errors}
    return do


SHORTCUTS = [
    ("the distance is rounded rather than floored", make_export(distance=distance_round)),
    ("the distance is rounded up", make_export(distance=distance_ceil)),
    ("the speed test is inclusive at the limit", make_export(speed=speed_inclusive)),
    ("the speed test divides, so a zero gap is never impossible", make_export(speed=speed_float)),
    ("a zero-second gap is never impossible", make_export(speed=speed_zero_never)),
    ("events are taken in the order the log was written", make_export(file_order=True)),
    ("events are ordered by id rather than by time", make_export(order_by_id=True)),
    ("the dedup window is exclusive at its boundary", make_export(dedup_exclusive=True)),
    ("duplicates are judged per user rather than per session", make_export(dedup_per_user=True)),
    ("a session keeps its first timestamp forever", make_export(dedup_no_reset=True)),
    ("a duplicate still establishes the location", make_export(duplicate_sets_location=True)),
    ("a failed sign-in establishes the location", make_export(failure_sets_location=True)),
    ("a failed sign-in is checked for travel", make_export(failure_checked=True)),
    ("a flagged sign-in does not become the previous location", make_export(flagged_not_previous=True)),
]


def main():
    sample_files = sorted(SAMPLES.glob("*.capture"))
    held_files = sorted(HELD_OUT.glob("*.capture"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.export_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.export_text(f.read_text(encoding="utf-8")) for f in held_files}

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
