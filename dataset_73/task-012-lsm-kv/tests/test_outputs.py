import json
import os

import pytest
from engine.engine import LsmKvEngine


def make(tmp_path, **cfg):
    cfg.setdefault("dir", str(tmp_path))
    return LsmKvEngine(cfg)


def test_put_get(tmp_path):
    e = make(tmp_path)
    e.put("a", "1")
    assert e.get("a") == "1"
    assert e.get("missing") is None


def test_overwrite(tmp_path):
    e = make(tmp_path)
    e.put("a", "1")
    e.put("a", "2")
    assert e.get("a") == "2" and e.size() == 1


def test_flush_on_capacity_creates_segment_and_clears_memtable(tmp_path):
    e = make(tmp_path, memtable_limit=3, level0_max=10)
    e.put("a", "1")
    e.put("b", "2")
    assert e.segment_count() == 0
    e.put("c", "3")                     # reaches the limit -> flush
    assert e.segment_count() == 1
    assert e.get("a") == "1" and e.get("c") == "3"


def test_explicit_flush_noop_when_empty(tmp_path):
    e = make(tmp_path)
    assert e.flush() is False
    e.put("a", "1")
    assert e.flush() is True
    assert e.flush() is False


def test_delete_tombstones_across_flush(tmp_path):
    e = make(tmp_path, memtable_limit=2, level0_max=10)
    e.put("a", "1")
    e.put("b", "2")                     # flush: {a,b}
    e.delete("a")
    e.put("c", "3")                     # flush: {a:tombstone, c}
    assert e.get("a") is None
    assert e.get("b") == "2" and e.get("c") == "3"
    assert e.size() == 2


def test_wal_truncated_after_flush(tmp_path):
    e = make(tmp_path, memtable_limit=2, level0_max=10)
    e.put("a", "1")
    e.put("b", "2")                     # triggers flush
    assert os.path.getsize(os.path.join(str(tmp_path), "wal.log")) == 0


def test_compaction_merges_segments(tmp_path):
    e = make(tmp_path, memtable_limit=1, level0_max=2)
    for k in ("a", "b", "c", "d"):      # 4 flushes -> exceeds level0_max -> compact
        e.put(k, k.upper())
    assert e.stats()["compactions"] >= 1
    assert e.segment_count() <= e.stats()["level0_max"] + 1
    assert [e.get(k) for k in "abcd"] == ["A", "B", "C", "D"]


def test_compaction_drops_tombstoned_keys(tmp_path):
    e = make(tmp_path, memtable_limit=1, level0_max=2)
    e.put("a", "1")
    e.put("b", "2")
    e.delete("a")
    e.put("c", "3")                     # 4 segments -> compact
    assert e.stats()["compactions"] >= 1
    assert e.get("a") is None and e.size() == 2
    assert all(k != "a" for k, _ in e.scan())


def test_compaction_keeps_newest_value_on_conflict(tmp_path):
    e = make(tmp_path, memtable_limit=1, level0_max=2)
    e.put("k", "old")
    e.put("x", "x")
    e.put("k", "new")
    e.put("y", "y")                     # compaction happens
    assert e.stats()["compactions"] >= 1
    assert e.get("k") == "new"


def test_size_counts_live_keys_only(tmp_path):
    e = make(tmp_path, memtable_limit=10, level0_max=10)
    e.put("a", "1")
    e.put("b", "2")
    e.put("c", "3")
    e.delete("b")
    assert e.size() == 2


def test_scan_range(tmp_path):
    e = make(tmp_path, memtable_limit=3, level0_max=10)
    for k in ("a", "b", "c", "d", "e"):
        e.put(k, k)
    assert e.scan("b", "d") == [("b", "b"), ("c", "c"), ("d", "d")]
    assert e.scan() == [(k, k) for k in ("a", "b", "c", "d", "e")]


def test_recovery_from_wal_and_segments(tmp_path):
    e = make(tmp_path, memtable_limit=2, level0_max=10)
    e.put("a", "1")
    e.put("b", "2")                     # flushed segment
    e.put("c", "3")                     # only in WAL + memtable
    e.close()
    e2 = make(tmp_path, memtable_limit=2, level0_max=10)
    assert e2.get("a") == "1" and e2.get("b") == "2" and e2.get("c") == "3"
    assert e2.size() == 3


def test_recovery_preserves_tombstones(tmp_path):
    e = make(tmp_path, memtable_limit=5, level0_max=10)
    e.put("a", "1")
    e.put("b", "2")
    e.delete("a")
    e.close()
    e2 = make(tmp_path, memtable_limit=5, level0_max=10)
    assert e2.get("a") is None and e2.get("b") == "2"


def test_reset_wipes_everything(tmp_path):
    e = make(tmp_path, memtable_limit=1, level0_max=5)
    for k in ("a", "b", "c"):
        e.put(k, k)
    e.reset()
    assert e.size() == 0 and e.segment_count() == 0
    assert e.get("a") is None


def test_configure_reinitialises(tmp_path):
    e = make(tmp_path, memtable_limit=2, level0_max=10)
    e.put("a", "1")
    e.configure({"memtable_limit": 5})
    assert e.size() == 0
    for i in range(4):
        e.put(f"c{i}", i)
    assert e.segment_count() == 0   # limit not reached
    e.put("c4", 4)
    assert e.segment_count() == 1   # 5th entry -> flush at new limit


@pytest.mark.parametrize("n", [5, 25, 100])
def test_bulk_put_get_consistency(tmp_path, n):
    e = make(tmp_path, memtable_limit=8, level0_max=3)
    for i in range(n):
        e.put(f"k{i:04d}", i)
    for i in range(n):
        assert e.get(f"k{i:04d}") == i
    assert e.size() == n


def test_get_after_delete_then_reput(tmp_path):
    e = make(tmp_path, memtable_limit=2, level0_max=10)
    e.put("a", "1")
    e.delete("a")
    e.put("a", "2")
    assert e.get("a") == "2" and e.size() == 1


# --------------------------------------------------------------- fixtures


def _write(d, name, obj):
    with open(os.path.join(d, name), "w", encoding="utf-8") as fp:
        json.dump(obj, fp)


def _write_log(d, records):
    with open(os.path.join(d, "wal.log"), "w", encoding="utf-8") as fp:
        for r in records:
            fp.write(json.dumps(r) + "\n")


def wrapped_store(tmp_path):
    """samples/wrapped_store: the 6-digit seq field has wrapped past 999999."""
    d = str(tmp_path)
    _write(d, "sst_999998.json", [["k1", "A998", False], ["k2", "B998", False],
                                  ["k3", "C998", False], ["k4", "D998", False]])
    _write(d, "sst_999999.json", [["k1", "A999", False], ["k2", "B999", False],
                                  ["k5", "E999", False], ["k6", "F999", False],
                                  ["k7", "G999", False], ["k8", None, True]])
    _write(d, "sst_000000.json", [["k2", "B000", False], ["k3", "C000", False],
                                  ["k5", "E000", False], ["k7", None, True],
                                  ["k8", "H000", False]])
    _write(d, "sst_000001.json", [["k1", "A001", False], ["k4", "D001", False],
                                  ["k6", None, True], ["k8", "H001", False]])
    _write(d, "manifest.json", {"version": 2, "segments": [
        {"file": "sst_999998.json", "level": 1},
        {"file": "sst_999999.json", "level": 1},
        {"file": "sst_000000.json", "level": 0},
        {"file": "sst_000001.json", "level": 0}]})
    _write_log(d, [])
    return d


WRAPPED_EXPECTED = {"k1": "A001", "k2": "B000", "k3": "C000", "k4": "D001",
                    "k5": "E000", "k6": None, "k7": None, "k8": "H001"}


def tombstone_layers(tmp_path):
    """samples/tombstone_layers: a retained tombstone above an older base."""
    d = str(tmp_path)
    _write(d, "sst_000007.json", [["a", "1", False], ["b", "2", False],
                                  ["z", "26", False]])
    _write(d, "sst_000011.json", [["a", None, True], ["c", "3", False]])
    _write(d, "manifest.json", {"version": 2, "segments": [
        {"file": "sst_000007.json", "level": 1},
        {"file": "sst_000011.json", "level": 1}]})
    _write_log(d, [])
    return d


def recycled_wal(tmp_path):
    """samples/recycled_wal: a log with leftovers from the previous epoch."""
    d = str(tmp_path)
    _write(d, "sst_000004.json", [["p1", "seg-1", False], ["p2", "seg-2", False],
                                  ["p3", "seg-3", False]])
    _write(d, "manifest.json", {"version": 2, "segments": [
        {"file": "sst_000004.json", "level": 1}]})
    _write_log(d, [
        [1, "p", "alpha", "a1"],
        [2, "p", "beta", "b1"],
        [3, "d", "p1", None],
        [4, "p", "alpha", "a2"],
        [5, "p", "delta", "d1"],
        [6, "d", "beta", None],
        [7, "p", "beta", "b2"],
        # everything from here on is left over from the previous epoch
        [3, "p", "alpha", "STALE-old"],
        [9, "p", "gamma", "STALE-new"],
        [10, "d", "p2", None],
        [11, "p", "delta", "STALE-delta"],
    ])
    return d


RECYCLED_EXPECTED = {"alpha": "a2", "beta": "b2", "delta": "d1", "gamma": None,
                     "p1": None, "p2": "seg-2", "p3": "seg-3",
                     "epsilon": None, "zeta": None, "omega": None}


def read_manifest(d):
    with open(os.path.join(d, "manifest.json"), "r", encoding="utf-8") as fp:
        return json.load(fp)


def read_rows(d, name):
    with open(os.path.join(d, name), "r", encoding="utf-8") as fp:
        return json.load(fp)


# ------------------------------------------------------- manifest (crux E)


def test_flush_writes_a_manifest_listing_the_segment(tmp_path):
    """A flush records its new segment in manifest.json (docs/manifest.md)."""
    e = make(tmp_path, memtable_limit=2, level0_max=10)
    e.put("a", "1")
    e.put("b", "2")
    man = read_manifest(str(tmp_path))
    files = [s["file"] for s in man["segments"]]
    assert len(files) == 1
    assert files[0].startswith("sst_") and files[0].endswith(".json")
    assert os.path.exists(os.path.join(str(tmp_path), files[0]))


def test_manifest_lists_segments_oldest_first(tmp_path):
    """manifest.json is ordered oldest -> newest, one entry per segment."""
    e = make(tmp_path, memtable_limit=1, level0_max=10)
    for k in ("a", "b", "c"):
        e.put(k, k)
    files = [s["file"] for s in read_manifest(str(tmp_path))["segments"]]
    assert len(files) == 3
    contents = [dict((r[0], r[1]) for r in read_rows(str(tmp_path), f))
                for f in files]
    assert list(contents[0]) == ["a"]
    assert list(contents[2]) == ["c"]


def test_manifest_order_beats_filename_order_on_reads(tmp_path):
    """get() resolves recency from manifest order, not from the filename seq."""
    d = wrapped_store(tmp_path)
    e = LsmKvEngine({"dir": d, "memtable_limit": 4, "level0_max": 3})
    assert {k: e.get(k) for k in WRAPPED_EXPECTED} == WRAPPED_EXPECTED


def test_wrapped_store_size_and_segment_count(tmp_path):
    """A wrapped store reports its six live keys and all four segments."""
    d = wrapped_store(tmp_path)
    e = LsmKvEngine({"dir": d, "memtable_limit": 4, "level0_max": 3})
    assert e.segment_count() == 4
    assert e.size() == 6
    assert [k for k, _ in e.scan()] == ["k1", "k2", "k3", "k4", "k5", "k8"]


def test_segment_numbers_stay_inside_the_six_digit_field(tmp_path):
    """The seq allocator is modulo 1000000 and skips numbers still in use."""
    d = wrapped_store(tmp_path)
    e = LsmKvEngine({"dir": d, "memtable_limit": 10, "level0_max": 10})
    e.put("new", "n")
    assert e.flush() is True
    names = [n for n in os.listdir(d) if n.startswith("sst_")]
    assert all(len(n) == len("sst_000000.json") for n in names), names
    assert "sst_000002.json" in names


def test_files_not_listed_in_the_manifest_are_not_part_of_the_store(tmp_path):
    """Recovery loads what the manifest lists, not what os.listdir returns."""
    d = wrapped_store(tmp_path)
    _write(d, "sst_000900.json", [["ghost", "boo", False]])
    e = LsmKvEngine({"dir": d, "memtable_limit": 4, "level0_max": 3})
    assert e.get("ghost") is None
    assert e.segment_count() == 4


def test_legacy_store_without_a_manifest_is_adopted(tmp_path):
    """A pre-manifest directory is adopted in filename order and gains a manifest."""
    d = str(tmp_path)
    _write(d, "sst_000001.json", [["a", "old", False], ["b", "B", False]])
    _write(d, "sst_000002.json", [["a", "new", False]])
    _write_log(d, [])
    e = LsmKvEngine({"dir": d, "memtable_limit": 10, "level0_max": 10})
    assert e.segment_count() == 2
    assert e.get("a") == "new" and e.get("b") == "B"
    e.put("c", "C")
    assert e.flush() is True
    files = [s["file"] for s in read_manifest(d)["segments"]]
    assert files[:2] == ["sst_000001.json", "sst_000002.json"]
    assert len(files) == 3


# ----------------------------------------------------- compaction (crux H)


def _store_with_retained_tombstone(tmp_path):
    """base level-1 segment holds a=1; a later minor compaction deletes a."""
    e = make(tmp_path, memtable_limit=1, level0_max=2)
    for k, v in (("a", "1"), ("b", "2"), ("c", "3")):
        e.put(k, v)                      # 3 level-0 flushes -> minor compaction
    assert e.segment_count() == 1
    e.delete("a")
    e.put("d", "4")
    e.put("e", "5")                      # 3 more flushes -> minor compaction
    return e


def test_minor_compaction_does_not_resurrect_a_deleted_key(tmp_path):
    """A compaction output that still shadows older segments keeps tombstones."""
    e = _store_with_retained_tombstone(tmp_path)
    assert e.get("a") is None
    assert e.get("b") == "2" and e.get("e") == "5"


def test_minor_compaction_output_still_carries_the_tombstone_row(tmp_path):
    """The retained tombstone is visible on disk as [key, null, true]."""
    e = _store_with_retained_tombstone(tmp_path)
    d = str(tmp_path)
    newest = read_manifest(d)["segments"][-1]["file"]
    rows = read_rows(d, newest)
    assert ["a", None, True] in rows


def test_no_resurrection_after_reopen(tmp_path):
    """The deleted key stays deleted for a brand-new engine on the same dir."""
    e = _store_with_retained_tombstone(tmp_path)
    e.close()
    e2 = make(tmp_path, memtable_limit=1, level0_max=2)
    assert e2.get("a") is None
    assert e2.size() == 4
    assert all(k != "a" for k, _ in e2.scan())


def test_tombstone_layers_sample(tmp_path):
    """A shipped two-generation store reads back exactly as documented."""
    d = tombstone_layers(tmp_path)
    e = LsmKvEngine({"dir": d, "memtable_limit": 4, "level0_max": 3})
    assert {k: e.get(k) for k in ("a", "b", "c", "z")} == {
        "a": None, "b": "2", "c": "3", "z": "26"}
    assert e.size() == 3 and e.segment_count() == 2


def test_explicit_compact_of_the_whole_store_drops_tombstones(tmp_path):
    """A merge of every segment is bottom-most, so tombstones may go."""
    e = _store_with_retained_tombstone(tmp_path)
    assert e.compact() is True
    d = str(tmp_path)
    files = [s["file"] for s in read_manifest(d)["segments"]]
    assert len(files) == 1
    rows = read_rows(d, files[0])
    assert all(r[2] is False for r in rows), rows
    assert [r[0] for r in rows] == ["b", "c", "d", "e"]
    assert e.get("a") is None


def test_major_compaction_collapses_the_level_one_run(tmp_path):
    """Too many level-1 segments merge into one base segment, tombstones gone."""
    e = make(tmp_path, memtable_limit=1, level0_max=2)
    for k, v in (("a", "1"), ("b", "2"), ("c", "3")):
        e.put(k, v)                      # minor compaction #1 -> base level 1
    e.delete("a")
    e.put("d", "4")
    e.put("e", "5")                      # minor compaction #2 -> level 1
    for k, v in (("f", "6"), ("g", "7"), ("h", "8")):
        e.put(k, v)                      # minor #3 -> 3 level-1 -> major
    assert e.segment_count() == 1
    assert e.stats()["compactions"] == 4
    d = str(tmp_path)
    files = [s["file"] for s in read_manifest(d)["segments"]]
    rows = read_rows(d, files[0])
    assert all(r[2] is False for r in rows), rows
    assert [r[0] for r in rows] == ["b", "c", "d", "e", "f", "g", "h"]
    assert e.get("a") is None and e.size() == 7


def test_compaction_counter_increments_per_pass(tmp_path):
    """stats()['compactions'] counts compaction passes since the last reset."""
    e = _store_with_retained_tombstone(tmp_path)
    before = e.stats()["compactions"]
    assert before == 2
    e.compact()
    assert e.stats()["compactions"] == before + 1


# ------------------------------------------------------------ wal (crux D)


def _log_lines(tmp_path):
    with open(os.path.join(str(tmp_path), "wal.log"), "r", encoding="utf-8") as fp:
        return [json.loads(l) for l in fp if l.strip()]


def test_wal_records_are_v2_shaped(tmp_path):
    """Records are [seq, op, key, val] with seq starting at 1 (docs/wal-format.md)."""
    e = make(tmp_path, memtable_limit=10, level0_max=10)
    e.put("a", "1")
    e.delete("b")
    e.put("c", "3")
    recs = _log_lines(tmp_path)
    assert [r[0] for r in recs] == [1, 2, 3]
    assert [r[1] for r in recs] == ["p", "d", "p"]
    assert recs[0] == [1, "p", "a", "1"]
    assert recs[1][2] == "b" and recs[1][3] is None


def test_wal_sequence_restarts_each_epoch(tmp_path):
    """Truncation starts a new epoch, so seq goes back to 1."""
    e = make(tmp_path, memtable_limit=2, level0_max=10)
    e.put("a", "1")
    e.put("b", "2")                      # flush -> truncate -> new epoch
    e.put("c", "3")
    assert [r[0] for r in _log_lines(tmp_path)] == [1]


def test_recovery_applies_only_the_live_tail_of_a_recycled_log(tmp_path):
    """Leftover records past the end of the epoch are discarded, not merged."""
    d = recycled_wal(tmp_path)
    e = LsmKvEngine({"dir": d, "memtable_limit": 100, "level0_max": 10})
    assert {k: e.get(k) for k in RECYCLED_EXPECTED} == RECYCLED_EXPECTED
    assert e.size() == 5


def test_recovery_ignores_a_stale_delete_in_the_leftover_tail(tmp_path):
    """A leftover tombstone must not erase a key the live tail never touched."""
    d = recycled_wal(tmp_path)
    e = LsmKvEngine({"dir": d, "memtable_limit": 100, "level0_max": 10})
    assert e.get("p2") == "seg-2"
    assert e.get("gamma") is None
    assert sorted(k for k, _ in e.scan()) == ["alpha", "beta", "delta",
                                              "p2", "p3"]


def test_recovery_stops_at_the_first_gap_in_the_sequence(tmp_path):
    """A missing seq is a torn write: nothing after it is applied."""
    d = str(tmp_path)
    _write_log(d, [[1, "p", "a", "1"], [2, "p", "b", "2"],
                   [4, "p", "c", "3"], [5, "p", "d", "4"]])
    e = LsmKvEngine({"dir": d, "memtable_limit": 100, "level0_max": 10})
    assert e.get("a") == "1" and e.get("b") == "2"
    assert e.get("c") is None and e.get("d") is None
    assert e.size() == 2


# -------------------------------------------------- memtable capacity trace


def test_flush_trigger_counts_buffered_writes_not_distinct_keys(tmp_path):
    """samples/trace_basic.jsonl: put a; put a; put b; put c flushes at limit 4."""
    e = make(tmp_path, memtable_limit=4, level0_max=3)
    e.put("a", "1")
    e.put("a", "2")
    assert e.stats()["memtable_entries"] == 1
    e.put("b", "2")
    assert e.segment_count() == 0
    e.put("c", "3")
    assert e.segment_count() == 1
    assert e.stats()["memtable_entries"] == 0
    assert e.get("a") == "2" and e.size() == 3


def test_repeated_deletes_of_one_key_still_reach_the_flush_trigger(tmp_path):
    """The counter is per write, so repeated writes to one key fill the MemTable."""
    e = make(tmp_path, memtable_limit=3, level0_max=10)
    e.put("k", "1")
    e.delete("k")
    assert e.segment_count() == 0
    e.put("k", "2")
    assert e.segment_count() == 1
    assert e.get("k") == "2" and e.size() == 1


@pytest.mark.parametrize("writes,expected_segments", [(4, 1), (12, 3), (16, 1)])
def test_trace_segment_counts(tmp_path, writes, expected_segments):
    """The captured session's segment_count after 4, 12 and 16 buffered writes."""
    e = make(tmp_path, memtable_limit=4, level0_max=3)
    for i in range(writes):
        e.put("k%02d" % i, i)
    assert e.segment_count() == expected_segments


# ------------------------------------------ further crux coverage (E, H, D)


def test_allocator_wraps_past_the_end_of_the_field(tmp_path):
    """The segment after sst_999999 is sst_000000, and it is the newest."""
    d = str(tmp_path)
    _write(d, "sst_999998.json", [["k", "v998", False]])
    _write(d, "sst_999999.json", [["k", "v999", False], ["m", "M", False]])
    _write(d, "manifest.json", {"version": 2, "segments": [
        {"file": "sst_999998.json", "level": 1},
        {"file": "sst_999999.json", "level": 1}]})
    _write_log(d, [])
    e = LsmKvEngine({"dir": d, "memtable_limit": 10, "level0_max": 10})
    e.put("k", "fresh")
    assert e.flush() is True
    assert [s["file"] for s in read_manifest(d)["segments"]] == [
        "sst_999998.json", "sst_999999.json", "sst_000000.json"]
    e.close()
    e2 = LsmKvEngine({"dir": d, "memtable_limit": 10, "level0_max": 10})
    assert e2.get("k") == "fresh"
    assert e2.get("m") == "M"
    assert e2.size() == 2


def test_tombstone_survives_a_second_minor_compaction(tmp_path):
    """A retained tombstone in a middle level-1 segment still hides the base."""
    e = make(tmp_path, memtable_limit=1, level0_max=3)
    for k in ("a", "b", "c", "d"):
        e.put(k, k.upper())              # 4 level-0 flushes -> minor #1 (base)
    e.delete("a")
    for k in ("e", "f", "g"):
        e.put(k, k.upper())              # 4 more flushes    -> minor #2
    for k in ("h", "i", "j", "k"):
        e.put(k, k.upper())              # 4 more flushes    -> minor #3
    assert e.segment_count() == 3
    assert e.get("a") is None and e.size() == 10
    d = str(tmp_path)
    middle = read_manifest(d)["segments"][1]["file"]
    assert ["a", None, True] in read_rows(d, middle)
    e.close()
    e2 = make(tmp_path, memtable_limit=1, level0_max=3)
    assert e2.get("a") is None
    assert e2.get("b") == "B" and e2.get("k") == "K"


def test_recovery_discards_a_log_that_does_not_start_at_seq_one(tmp_path):
    """A log holding nothing but leftovers contributes nothing to recovery."""
    d = str(tmp_path)
    _write(d, "sst_000000.json", [["a", "base", False]])
    _write(d, "manifest.json", {"version": 2, "segments": [
        {"file": "sst_000000.json", "level": 1}]})
    _write_log(d, [[5, "p", "a", "STALE"], [6, "d", "a", None],
                   [7, "p", "z", "STALE"]])
    e = LsmKvEngine({"dir": d, "memtable_limit": 100, "level0_max": 10})
    assert e.get("a") == "base"
    assert e.get("z") is None
    assert e.size() == 1


def test_recovery_stops_when_the_sequence_restarts_mid_file(tmp_path):
    """A second run of 1, 2, ... is the previous epoch, not more of this one."""
    d = str(tmp_path)
    _write_log(d, [[1, "p", "a", "1"], [2, "p", "b", "2"],
                   [1, "p", "a", "STALE"], [2, "d", "b", None]])
    e = LsmKvEngine({"dir": d, "memtable_limit": 100, "level0_max": 10})
    assert e.get("a") == "1" and e.get("b") == "2"
    assert e.size() == 2
