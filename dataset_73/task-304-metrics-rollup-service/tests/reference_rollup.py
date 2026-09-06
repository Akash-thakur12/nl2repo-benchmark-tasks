"""Reference model for metrics rollup, following docs/rollup-spec.md literally.

Section numbers in comments refer to that document. This is the authority for
expected output; nothing is hardcoded. The golden repository is written in Go
and must agree with this model exactly.
"""
import json


def series_key(name, labels):
    """1.3: the name, then ,key=value for each label in ascending key order."""
    parts = [name]
    for key in sorted(labels or {}):
        parts.append(",%s=%s" % (key, labels[key]))
    return "".join(parts)


def window_start(t, seconds):
    """2.2, 2.3: half-open windows, so a boundary sample starts a new one."""
    return (t // seconds) * seconds


def round_half_even(numerator, denominator):
    """3.2.2: nearest integer, exact halves to the even neighbour."""
    quotient, remainder = divmod(numerator, denominator)
    twice = 2 * remainder
    if twice > denominator:
        return quotient + 1
    if twice < denominator:
        return quotient
    return quotient + 1 if quotient % 2 else quotient


def group_series(samples):
    """1.2, 1.4: one bucket per series, samples sorted by time."""
    grouped = {}
    for sample in samples:
        key = series_key(sample["name"], sample.get("labels"))
        grouped.setdefault(key, {"type": sample["type"], "samples": []})
        grouped[key]["samples"].append(sample)
    for entry in grouped.values():
        entry["samples"].sort(key=lambda s: s["t"])
    return grouped


def counter_rows(samples, seconds):
    """3.1: each window reports the increase across it, resets included."""
    rows = []
    baseline = None                                  # 3.1.1 last value seen
    current_window = None
    delta = 0
    for sample in samples:
        start = window_start(sample["t"], seconds)
        if current_window is None:
            current_window = start
        elif start != current_window:
            rows.append({"window": current_window, "delta": delta})
            current_window = start
            delta = 0
        value = sample["value"]
        if baseline is None:
            pass                                     # 3.1.1 first ever sample
        elif value >= baseline:
            delta += value - baseline                # 3.1.2
        else:
            delta += value                           # 3.1.2 counter reset
        baseline = value
    if current_window is not None:
        rows.append({"window": current_window, "delta": delta})
    return rows


def gauge_rows(samples, seconds):
    """3.2."""
    buckets = {}
    order = []
    for sample in samples:
        start = window_start(sample["t"], seconds)
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
                     "avg": round_half_even(total, len(values))})
    return rows


def histogram_rows(samples, seconds):
    """3.3."""
    boundaries = samples[0]["boundaries"]
    for sample in samples:
        if sample["boundaries"] != boundaries:       # 3.3.2
            return None
    buckets = {}
    order = []
    for sample in samples:
        start = window_start(sample["t"], seconds)
        if start not in buckets:
            buckets[start] = [0] * len(boundaries)
            order.append(start)
        running = buckets[start]
        for index, count in enumerate(sample["counts"]):
            running[index] += count                  # 3.3.3
    return [{"window": start, "boundaries": list(boundaries),
             "counts": buckets[start]} for start in order]


def roll_counter(rows, seconds):
    """4.3."""
    totals = {}
    for row in rows:
        start = window_start(row["window"], seconds)  # 4.2
        totals[start] = totals.get(start, 0) + row["delta"]
    return [{"window": start, "delta": totals[start]} for start in sorted(totals)]


def roll_gauge(rows, seconds):
    """4.4: recomputed from the totals, never the mean of the lower averages."""
    groups = {}
    for row in rows:
        start = window_start(row["window"], seconds)
        groups.setdefault(start, []).append(row)
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
                    "avg": round_half_even(total, count)})
    return out


def roll_histogram(rows, seconds):
    """4.5."""
    groups = {}
    for row in rows:
        start = window_start(row["window"], seconds)
        groups.setdefault(start, []).append(row)
    out = []
    for start in sorted(groups):
        members = groups[start]
        boundaries = list(members[0]["boundaries"])
        counts = [0] * len(boundaries)
        for row in members:
            for index, value in enumerate(row["counts"]):
                counts[index] += value
        out.append({"window": start, "boundaries": boundaries, "counts": counts})
    return out


FIRST = {"counter": counter_rows, "gauge": gauge_rows, "histogram": histogram_rows}
LATER = {"counter": roll_counter, "gauge": roll_gauge, "histogram": roll_histogram}


def rollup(capture):
    tiers = capture["tiers"]
    grouped = group_series(capture.get("samples", []) or [])

    errors = []
    per_series = {}
    for key in sorted(grouped):
        entry = grouped[key]
        rows = FIRST[entry["type"]](entry["samples"], tiers[0]["seconds"])
        if rows is None:                             # 3.3.2 series drops out
            errors.append({"code": "BUCKET_MISMATCH", "series": key})
            continue
        per_series[key] = {"type": entry["type"], "tiers": [rows]}
        for tier in tiers[1:]:                       # 4.1 from the tier below
            previous = per_series[key]["tiers"][-1]
            per_series[key]["tiers"].append(
                LATER[entry["type"]](previous, tier["seconds"]))

    out = []
    for index, tier in enumerate(tiers):             # 5.1 tier, series, window
        for key in sorted(per_series):
            entry = per_series[key]
            for row in entry["tiers"][index]:
                record = {"tier": tier["name"], "series": key,
                          "type": entry["type"], "window": row["window"]}
                for field, value in row.items():
                    if field != "window":
                        record[field] = value
                out.append(record)

    return {"rows": out, "errors": errors}


def rollup_text(text):
    return rollup(json.loads(text))
