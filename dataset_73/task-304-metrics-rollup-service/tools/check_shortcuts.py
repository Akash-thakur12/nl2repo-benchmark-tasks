#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out capture catches it.

The golden repository is Go, but the near-misses are written against the Python
reference model, because that is the authority the tests derive expected output
from. Two of them are here precisely because they are what a Go implementation
reaches for by reflex: math.Round rounds halves away from zero, and integer
division truncates toward zero, neither of which is what the specification asks
for.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_rollup as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "captures"


# ------------------------------------------------------------ rounding variants
def round_half_up(numerator, denominator):
    quotient, remainder = divmod(numerator, denominator)
    return quotient + 1 if 2 * remainder >= denominator else quotient


def round_half_away(numerator, denominator):
    """What Go's math.Round does: halves go away from zero."""
    value = numerator / denominator
    if value >= 0:
        return int(value + 0.5)
    return -int(-value + 0.5)


def round_truncate(numerator, denominator):
    """What Go's integer division does: toward zero."""
    return int(numerator / denominator)


# -------------------------------------------------------------- window variants
def window_closed_left(t, seconds):
    """A boundary sample lands in the window that ends there."""
    if t % seconds == 0 and t != 0:
        return t - seconds
    return (t // seconds) * seconds


# -------------------------------------------------------------- series variants
def key_insertion_order(name, labels):
    parts = [name]
    for key in (labels or {}):
        parts.append(",%s=%s" % (key, labels[key]))
    return "".join(parts)


def key_without_labels(name, _labels):
    return name


# ------------------------------------------------------------ counter variants
def counter_last_minus_first(samples, seconds, _round):
    buckets, order = {}, []
    for sample in samples:
        start = ref.window_start(sample["t"], seconds)
        if start not in buckets:
            buckets[start] = []
            order.append(start)
        buckets[start].append(sample["value"])
    return [{"window": s, "delta": buckets[s][-1] - buckets[s][0]} for s in order]


def counter_no_carry(samples, seconds, _round):
    buckets, order = {}, []
    for sample in samples:
        start = ref.window_start(sample["t"], seconds)
        if start not in buckets:
            buckets[start] = []
            order.append(start)
        buckets[start].append(sample["value"])
    rows = []
    for start in order:
        values = buckets[start]
        total, previous = 0, None
        for value in values:
            if previous is None:
                pass                       # baseline restarts every window
            elif value >= previous:
                total += value - previous
            else:
                total += value
            previous = value
        rows.append({"window": start, "delta": total})
    return rows


def counter_reset_is_zero(samples, seconds, _round):
    rows, baseline, current, delta = [], None, None, 0
    for sample in samples:
        start = ref.window_start(sample["t"], seconds)
        if current is None:
            current = start
        elif start != current:
            rows.append({"window": current, "delta": delta})
            current, delta = start, 0
        value = sample["value"]
        if baseline is not None and value >= baseline:
            delta += value - baseline
        # a reset contributes nothing at all
        baseline = value
    if current is not None:
        rows.append({"window": current, "delta": delta})
    return rows


def counter_reset_on_equal(samples, seconds, _round):
    rows, baseline, current, delta = [], None, None, 0
    for sample in samples:
        start = ref.window_start(sample["t"], seconds)
        if current is None:
            current = start
        elif start != current:
            rows.append({"window": current, "delta": delta})
            current, delta = start, 0
        value = sample["value"]
        if baseline is None:
            pass
        elif value > baseline:             # equal counts as a reset
            delta += value - baseline
        else:
            delta += value
        baseline = value
    if current is not None:
        rows.append({"window": current, "delta": delta})
    return rows


# -------------------------------------------------------------- gauge variants
def gauge_file_order(samples, seconds, rounder):
    buckets, order = {}, []
    for sample in samples:
        start = ref.window_start(sample["t"], seconds)
        if start not in buckets:
            buckets[start] = []
            order.append(start)
        buckets[start].append(sample["value"])
    rows = []
    for start in order:
        values = buckets[start]
        total = sum(values)
        rows.append({"window": start, "min": min(values), "max": max(values),
                     "last": values[-1], "count": len(values), "sum": total,
                     "avg": rounder(total, len(values))})
    return rows


# ---------------------------------------------------------- histogram variants
def histogram_per_window_check(samples, seconds, _round):
    buckets, order = {}, []
    for sample in samples:
        start = ref.window_start(sample["t"], seconds)
        if start not in buckets:
            buckets[start] = []
            order.append(start)
        buckets[start].append(sample)
    rows = []
    for start in order:
        members = buckets[start]
        boundaries = members[0]["boundaries"]
        if any(m["boundaries"] != boundaries for m in members):
            return None                    # only a within-window disagreement counts
        counts = [0] * len(boundaries)
        for member in members:
            for index, value in enumerate(member["counts"]):
                counts[index] += value
        rows.append({"window": start, "boundaries": list(boundaries),
                     "counts": counts})
    return rows


# ----------------------------------------------------------- later-tier variants
def later_gauge_mean_of_avgs(rows, seconds, rounder):
    groups = {}
    for row in rows:
        groups.setdefault(ref.window_start(row["window"], seconds), []).append(row)
    out = []
    for start in sorted(groups):
        members = sorted(groups[start], key=lambda r: r["window"])
        out.append({"window": start,
                    "min": min(r["min"] for r in members),
                    "max": max(r["max"] for r in members),
                    "last": members[-1]["last"],
                    "count": sum(r["count"] for r in members),
                    "sum": sum(r["sum"] for r in members),
                    "avg": rounder(sum(r["avg"] for r in members), len(members))})
    return out


def later_gauge_first_last(rows, seconds, rounder):
    groups = {}
    for row in rows:
        groups.setdefault(ref.window_start(row["window"], seconds), []).append(row)
    out = []
    for start in sorted(groups):
        members = sorted(groups[start], key=lambda r: r["window"])
        total = sum(r["sum"] for r in members)
        count = sum(r["count"] for r in members)
        out.append({"window": start,
                    "min": min(r["min"] for r in members),
                    "max": max(r["max"] for r in members),
                    "last": members[0]["last"],          # earliest, not latest
                    "count": count, "sum": total,
                    "avg": rounder(total, count)})
    return out


def later_counter_last_delta(rows, seconds, _rounder):
    groups = {}
    for row in rows:
        groups.setdefault(ref.window_start(row["window"], seconds), []).append(row)
    return [{"window": start,
             "delta": sorted(groups[start], key=lambda r: r["window"])[-1]["delta"]}
            for start in sorted(groups)]


# --------------------------------------------------------------- the roller
def make_rollup(rounder=None, window_fn=None, key_fn=None, counter_fn=None,
                gauge_fn=None, histogram_fn=None, later_gauge=None,
                later_counter=None, higher_from_raw=False, emit_empty=False,
                sort_window_first=False, tier_not_primary=False,
                sort_samples=True):
    rounder = rounder or ref.round_half_even
    window_fn = window_fn or ref.window_start
    key_fn = key_fn or ref.series_key

    def first_tier(entry, seconds):
        kind = entry["type"]
        if kind == "counter":
            return (counter_fn or _default_counter)(entry["samples"], seconds, rounder)
        if kind == "gauge":
            return (gauge_fn or _default_gauge)(entry["samples"], seconds, rounder)
        return (histogram_fn or _default_hist)(entry["samples"], seconds, rounder)

    def _default_counter(samples, seconds, _r):
        rows, baseline, current, delta = [], None, None, 0
        for sample in samples:
            start = window_fn(sample["t"], seconds)
            if current is None:
                current = start
            elif start != current:
                rows.append({"window": current, "delta": delta})
                current, delta = start, 0
            value = sample["value"]
            if baseline is None:
                pass
            elif value >= baseline:
                delta += value - baseline
            else:
                delta += value
            baseline = value
        if current is not None:
            rows.append({"window": current, "delta": delta})
        return rows

    def _default_gauge(samples, seconds, r):
        buckets, order = {}, []
        for sample in samples:
            start = window_fn(sample["t"], seconds)
            if start not in buckets:
                buckets[start] = []
                order.append(start)
            buckets[start].append(sample["value"])
        rows = []
        for start in order:
            values = buckets[start]
            total = sum(values)
            rows.append({"window": start, "min": min(values), "max": max(values),
                         "last": values[-1], "count": len(values), "sum": total,
                         "avg": r(total, len(values))})
        return rows

    def _default_hist(samples, seconds, _r):
        boundaries = samples[0]["boundaries"]
        if any(s["boundaries"] != boundaries for s in samples):
            return None
        buckets, order = {}, []
        for sample in samples:
            start = window_fn(sample["t"], seconds)
            if start not in buckets:
                buckets[start] = [0] * len(boundaries)
                order.append(start)
            for index, value in enumerate(sample["counts"]):
                buckets[start][index] += value
        return [{"window": s, "boundaries": list(boundaries), "counts": buckets[s]}
                for s in order]

    def later(entry, rows, seconds):
        kind = entry["type"]
        if kind == "counter":
            return (later_counter or ref.roll_counter)(rows, seconds, rounder) \
                if later_counter else ref.roll_counter(rows, seconds)
        if kind == "gauge":
            if later_gauge:
                return later_gauge(rows, seconds, rounder)
            groups = {}
            for row in rows:
                groups.setdefault(window_fn(row["window"], seconds), []).append(row)
            out = []
            for start in sorted(groups):
                members = sorted(groups[start], key=lambda r: r["window"])
                total = sum(r["sum"] for r in members)
                count = sum(r["count"] for r in members)
                out.append({"window": start,
                            "min": min(r["min"] for r in members),
                            "max": max(r["max"] for r in members),
                            "last": members[-1]["last"],
                            "count": count, "sum": total,
                            "avg": rounder(total, count)})
            return out
        return ref.roll_histogram(rows, seconds)

    def do(capture):
        tiers = capture["tiers"]
        grouped = {}
        for sample in capture.get("samples", []) or []:
            key = key_fn(sample["name"], sample.get("labels"))
            grouped.setdefault(key, {"type": sample["type"], "samples": []})
            grouped[key]["samples"].append(sample)
        if sort_samples:
            for entry in grouped.values():
                entry["samples"].sort(key=lambda s: s["t"])

        errors, per_series = [], {}
        for key in sorted(grouped):
            entry = grouped[key]
            rows = first_tier(entry, tiers[0]["seconds"])
            if rows is None:
                errors.append({"code": "BUCKET_MISMATCH", "series": key})
                continue
            stack = [rows]
            for tier in tiers[1:]:
                if higher_from_raw:
                    stack.append(first_tier(entry, tier["seconds"]))
                else:
                    stack.append(later(entry, stack[-1], tier["seconds"]))
            per_series[key] = {"type": entry["type"], "tiers": stack}

        out = []
        for index, tier in enumerate(tiers):
            for key in sorted(per_series):
                entry = per_series[key]
                for row in entry["tiers"][index]:
                    record = {"tier": tier["name"], "series": key,
                              "type": entry["type"], "window": row["window"]}
                    for field, value in row.items():
                        if field != "window":
                            record[field] = value
                    out.append(record)
        if sort_window_first:
            out.sort(key=lambda r: (r["tier"], r["window"], r["series"]))
        if tier_not_primary:
            out.sort(key=lambda r: (r["series"], r["window"]))
        return {"rows": out, "errors": errors}
    return do


SHORTCUTS = [
    ("averages round halves up", make_rollup(rounder=round_half_up)),
    ("averages round halves away from zero, as math.Round does",
     make_rollup(rounder=round_half_away)),
    ("averages truncate toward zero", make_rollup(rounder=round_truncate)),
    ("a boundary sample closes the window it lands on",
     make_rollup(window_fn=window_closed_left)),
    ("the series key uses label insertion order", make_rollup(key_fn=key_insertion_order)),
    ("the series key ignores labels entirely", make_rollup(key_fn=key_without_labels)),
    ("a counter window reports last minus first", make_rollup(counter_fn=counter_last_minus_first)),
    ("the counter baseline restarts every window", make_rollup(counter_fn=counter_no_carry)),
    ("a counter reset contributes nothing", make_rollup(counter_fn=counter_reset_is_zero)),
    ("an unchanged counter counts as a reset", make_rollup(counter_fn=counter_reset_on_equal)),
    ("gauge fields are taken in file order", make_rollup(sort_samples=False)),
    ("histogram buckets are only checked within a window",
     make_rollup(histogram_fn=histogram_per_window_check)),
    ("a higher tier is computed from the raw samples again", make_rollup(higher_from_raw=True)),
    ("a higher-tier average is the mean of the lower averages",
     make_rollup(later_gauge=later_gauge_mean_of_avgs)),
    ("a higher-tier last comes from the earliest lower window",
     make_rollup(later_gauge=later_gauge_first_last)),
    ("a higher-tier counter takes the last lower delta",
     make_rollup(later_counter=later_counter_last_delta)),
    ("rows are ordered by window before series", make_rollup(sort_window_first=True)),
    ("rows are not grouped by tier first", make_rollup(tier_not_primary=True)),
]


def main():
    sample_files = sorted(SAMPLES.glob("*.capture"))
    held_files = sorted(HELD_OUT.glob("*.capture"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.rollup_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.rollup_text(f.read_text(encoding="utf-8")) for f in held_files}

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
