#!/usr/bin/env python3
"""aof_doctor - inspect a redis-lite append-only log.

Ops tool inherited with the legacy service. Point it at an aof.log and it
reports, per line, the byte offset, whether the record parses, and where the
last good record ends - which is the number you need when hand-repairing a file
or deciding whether a restart is safe.

    python aof_doctor.py ../samples/torn/aof.log

Exit status is 0 for a clean file, 1 for a file with any unreadable record.
"""
from __future__ import annotations

import json
import sys

ARITY = {"set": 3, "del": 2, "lpush": 3, "rpop": 2}


def classify(raw_line):
    """('ok', record) or ('bad', reason) for one stripped line."""
    try:
        record = json.loads(raw_line)
    except ValueError as exc:
        return "bad", "not valid JSON (%s)" % exc.args[0]
    if not isinstance(record, list) or not record:
        return "bad", "not a non-empty JSON array"
    opcode = record[0]
    if opcode not in ARITY:
        return "bad", "unknown opcode %r" % (opcode,)
    if len(record) != ARITY[opcode]:
        return "bad", "%r takes %d fields, got %d" % (opcode, ARITY[opcode], len(record))
    return "ok", record


def scan(path):
    with open(path, "rb") as handle:
        data = handle.read()

    ends_with_newline = data.endswith(b"\n")
    segments = data.split(b"\n")
    if ends_with_newline:
        segments = segments[:-1]

    offset = 0
    last_good_end = 0
    total = len(segments)
    bad = []

    for index, segment in enumerate(segments, start=1):
        start = offset
        offset += len(segment) + 1          # the newline, real or would-be
        text = segment.decode("utf-8", "replace").strip()
        if not text:
            last_good_end = offset
            print("  line %3d  offset %5d  blank" % (index, start))
            continue
        verdict, payload = classify(text)
        if verdict == "ok":
            last_good_end = offset
            print("  line %3d  offset %5d  ok    %s" % (index, start, payload[0]))
        else:
            bad.append((index, start, payload))
            print("  line %3d  offset %5d  BAD   %s" % (index, start, payload))

    print()
    print("  lines            : %d" % total)
    print("  bytes            : %d" % len(data))
    print("  ends with newline: %s" % ends_with_newline)
    print("  last good record ends at byte %d" % last_good_end)
    for index, start, reason in bad:
        print("  unreadable record at line %d of %d (byte %d): %s"
              % (index, total, start, reason))
    return bad


SUMMARY = """
diagnosis: replay ordering - LPUSH records are stored in arrival order but
head-insertion means the log must be replayed in REVERSE to reconstruct the
list; forward replay yields the list backwards. RPOP records must be reversed
with them or the replayed pop takes the wrong end. If a recovered list reads
back inverted, this is why; see docs/DEPRECATED-replay-notes-v1.md.
"""


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    bad = scan(argv[1])
    print(SUMMARY)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
