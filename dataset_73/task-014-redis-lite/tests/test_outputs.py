import pytest
from engine.engine import RedisLiteEngine, WrongTypeError


def make(tmp_path):
    return RedisLiteEngine({"dir": str(tmp_path)})


def test_string_set_get_delete(tmp_path):
    e = make(tmp_path)
    e.set("k", "v")
    assert e.get("k") == "v"
    assert e.delete("k") is True
    assert e.get("k") is None
    assert e.delete("k") is False


def test_get_missing_is_none(tmp_path):
    assert make(tmp_path).get("nope") is None


def test_exists(tmp_path):
    e = make(tmp_path)
    assert e.exists("k") is False
    e.set("k", "1")
    assert e.exists("k") is True
    e.lpush("L", "x")
    assert e.exists("L") is True


def test_lpush_prepends_and_returns_length(tmp_path):
    e = make(tmp_path)
    assert e.lpush("L", "a") == 1
    assert e.lpush("L", "b") == 2
    assert e.lpush("L", "c") == 3
    assert e.lrange("L", 0, -1) == ["c", "b", "a"]


def test_rpop(tmp_path):
    e = make(tmp_path)
    for x in "abc":
        e.lpush("L", x)          # [c, b, a]
    assert e.rpop("L") == "a"
    assert e.rpop("L") == "b"
    assert e.llen("L") == 1
    assert e.rpop("L") == "c"
    assert e.rpop("L") is None   # empty


def test_lrange_negative_and_out_of_range(tmp_path):
    e = make(tmp_path)
    for x in ["c", "b", "a"]:
        e.lpush("L", x)          # L = [a, b, c]
    assert e.lrange("L", 0, -1) == ["a", "b", "c"]
    assert e.lrange("L", -2, -1) == ["b", "c"]
    assert e.lrange("L", 1, 1) == ["b"]
    assert e.lrange("L", 5, 9) == []
    assert e.lrange("L", -100, 100) == ["a", "b", "c"]
    assert e.lrange("L", 2, 1) == []


def test_wrong_type_errors(tmp_path):
    e = make(tmp_path)
    e.set("s", "1")
    e.lpush("L", "x")
    with pytest.raises(WrongTypeError):
        e.get("L")
    with pytest.raises(WrongTypeError):
        e.set("L", "y")
    with pytest.raises(WrongTypeError):
        e.lpush("s", "z")
    with pytest.raises(WrongTypeError):
        e.rpop("s")


def test_delete_works_on_list_keys(tmp_path):
    e = make(tmp_path)
    e.lpush("L", "x")
    assert e.delete("L") is True
    assert e.exists("L") is False


def test_aof_persistence(tmp_path):
    e = make(tmp_path)
    e.set("a", "1")
    e.lpush("Q", "x")
    e.lpush("Q", "y")
    e.rpop("Q")
    e.close()
    e2 = make(tmp_path)
    assert e2.get("a") == "1"
    assert e2.lrange("Q", 0, -1) == ["y"]


def test_aof_replays_delete(tmp_path):
    e = make(tmp_path)
    e.set("a", "1")
    e.set("b", "2")
    e.delete("a")
    e.close()
    e2 = make(tmp_path)
    assert e2.get("a") is None and e2.get("b") == "2"


def test_reset_and_configure_wipe(tmp_path):
    e = make(tmp_path)
    e.set("a", "1")
    e.lpush("L", "x")
    e.reset()
    assert e.get("a") is None and e.lrange("L", 0, -1) == []
    e.set("b", "2")
    e.configure({})
    assert e.get("b") is None


@pytest.mark.parametrize("scenario", ["set/get", "set/del", "lpush/rpop", "multi-keys"])
def test_matrix(tmp_path, scenario):
    e = make(tmp_path)
    if scenario == "set/get":
        e.set("a", "1")
        assert e.get("a") == "1"
    elif scenario == "set/del":
        e.set("a", "1")
        assert e.delete("a") and e.get("a") is None
    elif scenario == "lpush/rpop":
        for i in range(3):
            e.lpush("L", str(i))
        assert e.rpop("L") == "0"
    else:
        e.set("a", "1")
        e.set("b", "2")
        assert e.get("a") == "1" and e.get("b") == "2"


# ---------------------------------------------------------------------------
# Recovery and durability. See environment/docs/aof-recovery.md and the
# captured logs under environment/samples/.
# ---------------------------------------------------------------------------

import json
import os

from engine.engine import AOFCorruptError


def seed(tmp_path, payload):
    """Write `payload` verbatim as the aof.log in tmp_path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "aof.log"
    log.write_bytes(payload.encode("utf-8"))
    return log


def records(tmp_path):
    """The log's non-empty lines, decoded."""
    raw = (tmp_path / "aof.log").read_text(encoding="utf-8")
    return [json.loads(l) for l in raw.splitlines() if l.strip()]


# -- replay ordering (samples/basic) ----------------------------------------

def test_replay_preserves_lpush_head_order(tmp_path):
    """Replay applies records in file order; LPUSH inserts at the head on the
    recovery path exactly as it does live, so `lpush a; lpush b` recovers as
    ["b", "a"] (samples/basic/expected_state.json)."""
    seed(tmp_path, '["set", "greeting", "hello"]\n'
                   '["lpush", "jobs", "a"]\n'
                   '["lpush", "jobs", "b"]\n')
    e = make(tmp_path)
    assert e.get("greeting") == "hello"
    assert e.lrange("jobs", 0, -1) == ["b", "a"]


def test_replay_rpop_removes_the_tail_not_the_head(tmp_path):
    """A replayed RPOP drops the same element the live RPOP dropped: the last
    one. Reversing the record stream would take the head instead."""
    seed(tmp_path, '["lpush", "L", "a"]\n'
                   '["lpush", "L", "b"]\n'
                   '["lpush", "L", "c"]\n'
                   '["rpop", "L"]\n')
    e = make(tmp_path)
    assert e.lrange("L", 0, -1) == ["c", "b"]


# -- invariant S2: a list key exists iff its list is non-empty --------------

def test_replay_drops_an_emptied_list_key(tmp_path):
    """samples/emptied: after replaying an emptying RPOP the key is absent from
    both keyspaces, not bound to []."""
    seed(tmp_path, '["set", "keep", "1"]\n'
                   '["lpush", "L", "x"]\n'
                   '["rpop", "L"]\n')
    e = make(tmp_path)
    assert e.get("keep") == "1"
    assert e.exists("L") is False
    assert e.llen("L") == 0
    assert e.lrange("L", 0, -1) == []


def test_replayed_empty_list_does_not_poison_the_string_keyspace(tmp_path):
    """A key left bound to an empty list by replay would claim the name in the
    list keyspace, so a later SET on it would raise WRONGTYPE against a list
    nobody can see. It must not."""
    seed(tmp_path, '["lpush", "L", "x"]\n["rpop", "L"]\n')
    e = make(tmp_path)
    e.set("L", "v")
    assert e.get("L") == "v"


def test_emptied_list_key_is_gone_after_a_real_restart(tmp_path):
    """The same invariant driven through the live path and a genuine restart
    rather than a hand-written log."""
    e = make(tmp_path)
    e.lpush("L", "x")
    assert e.rpop("L") == "x"
    e.close()
    e2 = make(tmp_path)
    assert e2.exists("L") is False
    assert e2.llen("L") == 0


# -- torn tail (samples/torn) ----------------------------------------------

def test_torn_final_record_is_discarded(tmp_path):
    """A partial final record with no terminating newline is a torn write from
    a crash: it contributes nothing to the recovered state."""
    seed(tmp_path, '["set", "a", "1"]\n'
                   '["lpush", "Q", "j1"]\n'
                   '["set", "z", "12')
    e = make(tmp_path)
    assert e.get("a") == "1"
    assert e.lrange("Q", 0, -1) == ["j1"]
    assert e.get("z") is None


def test_torn_final_record_is_truncated_from_the_file(tmp_path):
    """Construction truncates the log back to the end of the last good record
    (samples/torn/after_restart.json: 396 bytes before, 380 after)."""
    good = '["set", "a", "1"]\n["lpush", "Q", "j1"]\n'
    seed(tmp_path, good + '["set", "z", "12')
    make(tmp_path)
    raw = (tmp_path / "aof.log").read_bytes()
    assert b'"z"' not in raw
    assert len(raw) == len(good)


def test_torn_log_round_trips_across_a_second_restart(tmp_path):
    """The reason truncation matters: a fragment left on disk gets the next
    appended record glued onto it, losing that write on the following
    restart."""
    seed(tmp_path, '["set", "a", "1"]\n["set", "z", "12')
    e = make(tmp_path)
    e.set("q", "1")
    e.close()
    e2 = make(tmp_path)
    assert e2.get("q") == "1"
    assert e2.get("a") == "1"
    assert e2.get("z") is None


def test_empty_and_missing_logs_are_not_torn(tmp_path):
    """A missing log and a zero-byte log are ordinary cold starts, not
    damage."""
    e = make(tmp_path)
    e.close()
    seed(tmp_path, "")
    e2 = make(tmp_path)
    assert e2.get("anything") is None
    e2.set("a", "1")
    e2.close()
    assert records(tmp_path) == [["set", "a", "1"]]


# -- corrupt interior (samples/corrupt) ------------------------------------

def test_corrupt_interior_record_refuses_to_start(tmp_path):
    """A malformed record that is not the unterminated final line cannot be a
    torn write; the engine raises AOFCorruptError instead of replaying around
    it (samples/corrupt/expected_error.txt)."""
    seed(tmp_path, '["set", "a", "1"]\n'
                   '["set", "b"\n'
                   '["set", "c", "3"]\n')
    with pytest.raises(AOFCorruptError):
        make(tmp_path)


def test_corrupt_log_is_left_untouched(tmp_path):
    """Refusing to start must not modify or truncate the damaged file - an
    operator still has to repair it."""
    payload = '["set", "a", "1"]\n["set", "b"\n["set", "c", "3"]\n'
    seed(tmp_path, payload)
    with pytest.raises(AOFCorruptError):
        make(tmp_path)
    assert (tmp_path / "aof.log").read_text(encoding="utf-8") == payload


def test_terminated_malformed_final_line_is_corruption(tmp_path):
    """A malformed last line that *is* newline-terminated was fully written, so
    it is damage rather than a torn tail."""
    seed(tmp_path, '["set", "a", "1"]\n["set", "b"\n')
    with pytest.raises(AOFCorruptError):
        make(tmp_path)


def test_unknown_opcode_and_bad_arity_are_malformed(tmp_path):
    """'malformed' covers valid JSON with an unknown opcode or the wrong number
    of fields, not only unparsable text."""
    seed(tmp_path, '["set", "a", "1"]\n["rename", "a", "b"]\n')
    with pytest.raises(AOFCorruptError):
        make(tmp_path)
    seed(tmp_path, '["set", "a", "1"]\n["rpop", "L", "extra"]\n')
    with pytest.raises(AOFCorruptError):
        make(tmp_path)
    seed(tmp_path, '["set", "a", "1"]\n[]\n')
    with pytest.raises(AOFCorruptError):
        make(tmp_path)
    seed(tmp_path, '["set", "a", "1"]\n{"op": "set"}\n')
    with pytest.raises(AOFCorruptError):
        make(tmp_path)


def test_blank_lines_in_the_log_are_not_records(tmp_path):
    """A blank line carries no command, so it is skipped rather than treated as
    damage - including a blank line between good records."""
    seed(tmp_path, '["set", "a", "1"]\n\n["lpush", "L", "x"]\n\n')
    e = make(tmp_path)
    assert e.get("a") == "1"
    assert e.lrange("L", 0, -1) == ["x"]
    e.set("b", "2")
    e.close()
    assert records(tmp_path)[-1] == ["set", "b", "2"]


# -- invariant L1: every record in the log is a mutation that was applied ---

def test_rejected_command_is_not_logged(tmp_path):
    """samples/rejected: the SET / rejected LPUSH / GET / no-op DEL / SET
    session produced a two-record log, so the type check runs before the
    append."""
    e = make(tmp_path)
    e.set("s", "1")
    with pytest.raises(WrongTypeError):
        e.lpush("s", "z")
    assert e.get("s") == "1"
    assert e.delete("missing") is False
    e.set("s", "2")
    e.close()
    assert records(tmp_path) == [["set", "s", "1"], ["set", "s", "2"]]


def test_reads_and_noop_delete_do_not_grow_the_log(tmp_path):
    """Reads and a delete of a missing key change nothing, so they append
    nothing."""
    e = make(tmp_path)
    e.lpush("L", "x")
    e.close()
    size = os.path.getsize(str(tmp_path / "aof.log"))
    e2 = make(tmp_path)
    e2.llen("L")
    e2.lrange("L", 0, -1)
    e2.exists("L")
    e2.get("nothing")
    assert e2.delete("nothing") is False
    assert e2.rpop("empty-list") is None
    e2.close()
    assert os.path.getsize(str(tmp_path / "aof.log")) == size


def test_rejected_lpush_does_not_resurrect_the_key_after_restart(tmp_path):
    """The second-order failure that logging-before-validating causes: the
    rejected record replays and recreates a string key as a list as well, after
    which every read of that key raises."""
    e = make(tmp_path)
    e.set("s", "1")
    with pytest.raises(WrongTypeError):
        e.lpush("s", "z")
    e.close()
    e2 = make(tmp_path)
    assert e2.get("s") == "1"
    assert e2.exists("s") is True
    assert e2.lrange("nothing-here", 0, -1) == []
