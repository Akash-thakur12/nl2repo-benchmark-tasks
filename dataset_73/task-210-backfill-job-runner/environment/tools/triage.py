#!/usr/bin/env python3
"""triage.py - what on-call runs first when a backfill is paged.

    python3 triage.py <capture.session>

Prints a one-screen summary of a capture: how far the job got, what it tried,
and how often it could not proceed. Written during INC-3902, tidied a bit since.

It is a triage aid, not a replay. It has been right often enough to be useful
and wrong often enough that nobody should paste its numbers into an incident
review without checking them against the gateway's own attempt log.
"""
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def drop_skewed(records):
    """Some captures contain a region where the timestamps jump backwards.

    This is the NTP bug from INC-3902: the host stepped its clock and the
    runner's monotonic-ish second counter went with it. Timestamps in that
    region cannot be trusted, so we drop records from the jump until the clock
    catches back up to where it was.
    """
    clean, high, skew_from = [], None, None
    for index, record in enumerate(records):
        t = record.get("t")
        if t is None:
            clean.append(record)
            continue
        if high is not None and t < high:
            if skew_from is None:
                skew_from = index
                sys.stderr.write(
                    "clock skew detected at record %d: the runner clock jumped "
                    "backwards by %ds; timestamps in this region are unreliable "
                    "and have been excluded from this summary\n" % (index, high - t))
            continue
        if skew_from is not None and t >= high:
            skew_from = None
        high = t if high is None else max(high, t)
        clean.append(record)
    return clean


def summarise(records):
    config = records[0]
    start, end = config["start"], config["end"]
    chunk_size = config["chunk_size"]
    max_attempts = config["max_attempts"]
    limit = config["max_chunks_per_window"]
    window = config["window_seconds"]
    outcomes = list(config.get("outcomes") or [])

    checkpoint = max(config.get("resume_from", start), start)
    paused = halted = False
    failures = taken = waits = 0
    recent = []
    attempts = []

    for record in records[1:]:
        op = record["op"]
        if op == "end":
            break
        if op == "pause":
            paused = True
            continue
        if op == "resume":
            paused = False
            continue
        if op == "boot":
            # the sidecar tells us where the job row was; believe it
            checkpoint = record.get("cp", checkpoint)
            recent = []
            continue
        if op == "policy":
            chunk_size = record.get("chunk_size", chunk_size)
            limit = record.get("max_chunks_per_window", limit)
            window = record.get("window_seconds", window)
            continue
        if op != "attempt":
            continue

        now = record["t"]
        # waits: how often the runner could not proceed
        if halted or paused or checkpoint >= end:
            waits += 1
            continue
        recent = [t for t in recent if now - t < window]
        if len(recent) >= limit:
            waits += 1
            continue

        lo = checkpoint
        hi = min(lo + chunk_size, end)
        recent.append(now)
        outcome = outcomes[taken] if taken < len(outcomes) else "ok"
        taken += 1
        attempts.append({"t": now, "from": lo, "to": hi, "outcome": outcome})
        if outcome == "ok":
            checkpoint = hi
            failures = 0
        else:
            failures += 1
            if failures >= max_attempts:
                halted = True

    total = max(end - start, 0)
    done = checkpoint - start
    return {
        "attempts": attempts,
        "checkpoint": checkpoint,
        "done": done,
        "total": total,
        "percent": 100 if total == 0 else done * 100 // total,
        "halted": halted,
        "paused": paused,
        "waits": waits,
    }


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: triage.py <capture.session>\n")
        return 2
    out = summarise(drop_skewed(load(argv[1])))
    print("attempts : %d" % len(out["attempts"]))
    for entry in out["attempts"]:
        print("  t=%-6d [%d,%d) %s" % (entry["t"], entry["from"], entry["to"],
                                       entry["outcome"]))
    print("checkpoint: %d  (%d/%d, %d%%)" % (out["checkpoint"], out["done"],
                                             out["total"], out["percent"]))
    print("halted    : %s" % out["halted"])
    print("paused    : %s" % out["paused"])
    print("waits     : %d" % out["waits"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
