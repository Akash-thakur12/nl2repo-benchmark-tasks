"""A small log-structured merge-tree key/value store.

MemTable (dict) -> WAL for durability -> capacity-triggered flush to sorted
on-disk SSTable segments -> levelled compaction.

Three details of the on-disk format drive the shape of this file:

* the 6-digit ``sst_<seq>.json`` field wraps at 1_000_000, so ``manifest.json``
  is the only authority on segment recency and level (docs/manifest.md);
* a compaction output that still shadows older segments may not discard
  tombstones (docs/compaction.md);
* the WAL file is recycled on truncate, so recovery applies only the contiguous
  ``seq`` prefix of the log (docs/wal-format.md).
"""
from __future__ import annotations

import json
import os

from engine.wal import WriteAheadLog

_TOMBSTONE = {"__tombstone__": True}

SEQ_MODULUS = 1000000
SEQ_WIDTH = 6
MANIFEST_NAME = "manifest.json"


class LsmKvEngine:
    def __init__(self, config=None):
        cfg = config or {}
        self._dir = cfg.get("dir", "lsm_data")
        self._memtable_limit = cfg.get("memtable_limit", 4)
        self._level0_max = cfg.get("level0_max", 3)
        os.makedirs(self._dir, exist_ok=True)
        self._mem = {}
        # oldest -> newest; each entry {"seq": int, "level": int, "data": dict}
        self._segments = []
        self._compactions = 0
        self._pending = 0          # buffered writes since the last flush
        self._wal_seq = 0          # last seq handed to the WAL in this epoch
        self._load_segments()
        self._wal = WriteAheadLog(self._wal_path())
        self._replay()

    # ----------------------------------------------------------- paths / io
    def _wal_path(self):
        return os.path.join(self._dir, "wal.log")

    def _manifest_path(self):
        return os.path.join(self._dir, MANIFEST_NAME)

    def _seg_name(self, seq):
        return "sst_%06d.json" % seq

    def _seg_path(self, seq):
        return os.path.join(self._dir, self._seg_name(seq))

    @staticmethod
    def _seq_of(name):
        return int(name[4:-5])

    def _read_segment(self, name):
        with open(os.path.join(self._dir, name), "r", encoding="utf-8") as fp:
            return {k: (_TOMBSTONE if t else v) for k, v, t in json.load(fp)}

    def _write_segment(self, seq, data):
        rows = [
            [k, (None if v is _TOMBSTONE else v), v is _TOMBSTONE]
            for k, v in sorted(data.items())
        ]
        with open(self._seg_path(seq), "w", encoding="utf-8") as fp:
            json.dump(rows, fp)

    # ------------------------------------------------------------- manifest
    def _write_manifest(self):
        payload = {
            "version": 2,
            "segments": [
                {"file": self._seg_name(s["seq"]), "level": s["level"]}
                for s in self._segments
            ],
        }
        tmp = self._manifest_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(payload, fp)
        os.replace(tmp, self._manifest_path())

    def _load_segments(self):
        """Recover the segment list.

        The manifest is the authority on order and level; filenames are not,
        because the sequence field wraps.  A directory that holds segments but
        no manifest is a legacy store, adopted in filename order.
        """
        self._segments = []
        entries = None
        try:
            with open(self._manifest_path(), "r", encoding="utf-8") as fp:
                entries = json.load(fp).get("segments", [])
        except (OSError, ValueError):
            entries = None

        if entries is None:
            names = sorted(
                n for n in os.listdir(self._dir)
                if n.startswith("sst_") and n.endswith(".json")
            )
            entries = [{"file": n, "level": 0} for n in names]

        for ent in entries:
            name = ent["file"]
            if not os.path.exists(os.path.join(self._dir, name)):
                continue
            self._segments.append({
                "seq": self._seq_of(name),
                "level": int(ent.get("level", 0)),
                "data": self._read_segment(name),
            })

    def _alloc_seq(self, extra_live=()):
        """Next segment number: newest + 1, modulo the width of the field."""
        live = {s["seq"] for s in self._segments}
        live.update(extra_live)
        if not self._segments:
            seq = 0
        else:
            seq = (self._segments[-1]["seq"] + 1) % SEQ_MODULUS
        while seq in live:
            seq = (seq + 1) % SEQ_MODULUS
        return seq

    # ------------------------------------------------------------------ wal
    def _replay(self):
        """Apply the live tail of the log: the maximal 1,2,3,... seq prefix.

        The log file is recycled, so records written during an earlier epoch can
        sit past the end of this epoch's records.  They parse fine and they look
        plausible, so the only sound rule is to stop at the first record whose
        seq is not the one expected next, and discard the remainder.
        """
        applied = 0
        expected = 1
        for rec in self._wal.replay():
            if not isinstance(rec, list) or len(rec) != 4:
                break
            seq, op, key, val = rec
            if seq != expected:
                break
            if op == "p":
                self._mem[key] = val
            elif op == "d":
                self._mem[key] = _TOMBSTONE
            else:
                break
            expected += 1
            applied += 1
        self._wal_seq = applied
        self._pending = applied

    def _log(self, op, key, val):
        self._wal_seq += 1
        self._wal.append([self._wal_seq, op, key, val])

    # ------------------------------------------------------------------ api
    def put(self, key, val):
        self._log("p", key, val)
        self._mem[key] = val
        self._pending += 1
        self._maybe_flush()

    def delete(self, key):
        self._log("d", key, None)
        self._mem[key] = _TOMBSTONE
        self._pending += 1
        self._maybe_flush()

    def get(self, key):
        if key in self._mem:
            v = self._mem[key]
            return None if v is _TOMBSTONE else v
        for seg in reversed(self._segments):       # newest -> oldest
            if key in seg["data"]:
                v = seg["data"][key]
                return None if v is _TOMBSTONE else v
        return None

    def _maybe_flush(self):
        if self._pending >= self._memtable_limit:
            self.flush()

    def flush(self):
        if not self._mem:
            return False
        seq = self._alloc_seq()
        self._write_segment(seq, self._mem)
        self._segments.append({"seq": seq, "level": 0, "data": dict(self._mem)})
        self._write_manifest()
        self._mem = {}
        self._pending = 0
        self._wal.truncate()
        self._wal_seq = 0
        self._maybe_compact()
        return True

    # ----------------------------------------------------------- compaction
    def _count_level(self, level):
        return sum(1 for s in self._segments if s["level"] == level)

    def _maybe_compact(self):
        if self._count_level(0) > self._level0_max:
            self._minor_compact()
        if self._count_level(1) > self._level0_max:
            self._major_compact()

    @staticmethod
    def _merge(segments, drop_tombstones):
        merged = {}
        for seg in segments:                       # oldest -> newest
            merged.update(seg["data"])
        if drop_tombstones:
            merged = {k: v for k, v in merged.items() if v is not _TOMBSTONE}
        return merged

    def _run_compaction(self, inputs, below, above):
        """Merge ``inputs`` into one level-1 segment sitting between the
        segments in ``below`` (older) and ``above`` (newer).

        Tombstones may only be discarded when nothing survives below the output.
        Any older segment left on disk is still consulted by ``get``, so an
        output that still shadows one would resurrect a deleted key if it threw
        the tombstone away.
        """
        if not inputs:
            return False
        self._compactions += 1
        merged = self._merge(inputs, drop_tombstones=not below)
        survivors = list(below) + list(above)
        for seg in inputs:
            try:
                os.remove(self._seg_path(seg["seq"]))
            except OSError:
                pass
        self._segments = list(below)
        seq = self._alloc_seq(extra_live={s["seq"] for s in survivors})
        self._write_segment(seq, merged)
        out = {"seq": seq, "level": 1, "data": merged}
        self._segments = list(below) + [out] + list(above)
        self._write_manifest()
        return True

    def _minor_compact(self):
        """The level-0 run becomes one level-1 segment above the older ones."""
        inputs = [s for s in self._segments if s["level"] == 0]
        below = [s for s in self._segments if s["level"] != 0]
        return self._run_compaction(inputs, below, [])

    def _major_compact(self):
        """Every level-1 segment becomes the single base segment of the store."""
        inputs = [s for s in self._segments if s["level"] == 1]
        above = [s for s in self._segments if s["level"] != 1]
        return self._run_compaction(inputs, [], above)

    def compact(self):
        """Merge every current segment into one."""
        inputs = list(self._segments)
        if not inputs:
            return True
        self._run_compaction(inputs, [], [])
        return True

    # ---------------------------------------------------------------- views
    def _view(self):
        view = {}
        for seg in self._segments:                 # oldest -> newest
            view.update(seg["data"])
        view.update(self._mem)
        return view

    def size(self):
        return sum(1 for v in self._view().values() if v is not _TOMBSTONE)

    def scan(self, lo=None, hi=None):
        view = self._view()
        out = []
        for k in sorted(view):
            if view[k] is _TOMBSTONE:
                continue
            if lo is not None and k < lo:
                continue
            if hi is not None and k > hi:
                continue
            out.append((k, view[k]))
        return out

    def stats(self):
        return {
            "segments": len(self._segments),
            "memtable_entries": len(self._mem),
            "compactions": self._compactions,
            "memtable_limit": self._memtable_limit,
            "level0_max": self._level0_max,
        }

    def segment_count(self):
        return len(self._segments)

    def close(self):
        try:
            self._wal.close()
        except Exception:
            pass

    def reset(self):
        self.close()
        for name in os.listdir(self._dir):
            try:
                os.remove(os.path.join(self._dir, name))
            except OSError:
                pass
        self._mem = {}
        self._segments = []
        self._compactions = 0
        self._pending = 0
        self._wal_seq = 0
        self._wal = WriteAheadLog(self._wal_path())
        self._wal.truncate()

    def configure(self, options):
        options = options or {}
        self._memtable_limit = options.get("memtable_limit", self._memtable_limit)
        self._level0_max = options.get("level0_max", self._level0_max)
        self.reset()
