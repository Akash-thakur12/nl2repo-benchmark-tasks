#!/usr/bin/env python3
"""lsm_doctor - read-only triage for an LSM store directory.

    usage: python tools/lsm_doctor.py <store-dir>

Written during the incident review that produced the two known failure modes
recorded against this engine:

    * "Reading from an older SSTable/segment before the memtable or a newer
       segment, returning a stale value instead of the most recent write."
    * "WAL replay not correctly reconstructing tombstone deletes, resurrecting
       a key that was deleted before the crash."

The tool opens nothing for writing and changes nothing on disk.  It reads the
segment files and the log, applies the heuristics below, and prints what it
finds.  Findings are heuristics, not proofs.

  H1  If replaying the log in file order and reading the segments in filename
      order disagree about any key, the read path is consulting segments in the
      wrong direction.
  H2  If the numeric order of the segment filenames does not match the order in
      which the catalogue lists them, the segment numbering has drifted and
      should be renormalised by a compaction pass.
"""
import json
import os
import sys


def _load_rows(path):
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def _segment_files(d):
    return sorted(n for n in os.listdir(d)
                  if n.startswith("sst_") and n.endswith(".json"))


def _replay_all(path):
    """Every record in the file, in file order (see docs/ARCHIVE/wal-format-v1.md)."""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    d = argv[1]
    names = _segment_files(d)
    print(f"store        : {d}")
    print(f"segments     : {len(names)}")
    for n in names:
        rows = _load_rows(os.path.join(d, n))
        tomb = sum(1 for r in rows if r[2])
        print(f"  {n}  rows={len(rows):3d}  tombstones={tomb}")

    log = _replay_all(os.path.join(d, "wal.log"))
    print(f"wal records  : {len(log)}")

    findings = []

    # --- H1 -------------------------------------------------------------
    by_name = {}
    for n in names:
        for k, v, t in _load_rows(os.path.join(d, n)):
            by_name[k] = None if t else v
    from_log = {}
    for rec in log:
        if len(rec) == 4:
            _seq, op, k, v = rec
            from_log[k] = None if op == "d" else v
    clash = [k for k in from_log if k in by_name and by_name[k] != from_log[k]]
    if clash:
        findings.append(
            "read-path recency inversion - segments appear to be consulted "
            f"oldest-first; check get() ordering (keys: {sorted(clash)[:4]})")

    # --- H2 -------------------------------------------------------------
    listed = []
    try:
        with open(os.path.join(d, "manifest.json"), "r", encoding="utf-8") as fp:
            listed = [s["file"] for s in json.load(fp).get("segments", [])]
    except (OSError, ValueError):
        listed = []
    if listed and listed != sorted(listed):
        findings.append(
            "segment sequence numbers are out of order on disk; "
            "run a compaction to renumber")

    if not findings:
        print("no findings")
    for f in findings:
        print(f"FINDING: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
