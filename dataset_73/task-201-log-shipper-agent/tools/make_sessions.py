#!/usr/bin/env python3
"""Regenerate the sample and held-out session corpora, and samples/expected.json.

The two corpora have opposite jobs.

  samples/   Six captures from a well-behaved host. Whole lines only, flushes
             driven purely by max_lines, every batch answered 200 in order, no
             rotation while lines are pending, no restart, spool never near full.
             Under these conditions almost every plausible shortcut reproduces
             expected.json byte for byte.

  tests/sessions/  Held-out captures that exercise everything the specification
             describes: unterminated fragments, age and byte flush triggers,
             rotation with pending lines, transient failures and the front
             requeue, retry exhaustion, permanent rejects, stale batch ids,
             backpressure dropping the oldest lines, restart re-reading from the
             acked offset, and out-of-order responses.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_shipper  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"

BENIGN_CFG = {"op": "config", "max_lines": 3, "max_bytes": 4096,
              "max_age_ms": 100000, "max_retries": 3, "spool_max_bytes": 65536}


def lines(*items):
    return "".join(s + "\n" for s in items)


# ------------------------------------------------------------ benign samples
def benign():
    s = {}

    s["s01"] = [BENIGN_CFG,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("boot ok", "listening on 8080", "ready")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "end", "t": 30}]

    s["s02"] = [BENIGN_CFG,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("a1", "a2", "a3")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "append", "t": 30, "file": "app.log", "data": lines("a4", "a5", "a6")},
                {"op": "response", "t": 40, "batch": 2, "status": 200},
                {"op": "end", "t": 50}]

    s["s03"] = [BENIGN_CFG,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("x1", "x2", "x3")},
                {"op": "append", "t": 15, "file": "app.log", "data": lines("x4", "x5", "x6")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "response", "t": 21, "batch": 2, "status": 200},
                {"op": "end", "t": 30}]

    s["s04"] = [BENIGN_CFG,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("p1", "p2", "p3")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "tick", "t": 100},
                {"op": "append", "t": 110, "file": "app.log", "data": lines("q1", "q2", "q3")},
                {"op": "response", "t": 120, "batch": 2, "status": 200},
                {"op": "end", "t": 130}]

    s["s05"] = [BENIGN_CFG,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("m1", "m2", "m3")},
                {"op": "append", "t": 11, "file": "audit.log", "data": lines("u1", "u2", "u3")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "response", "t": 21, "batch": 2, "status": 200},
                {"op": "end", "t": 30}]

    s["s06"] = [BENIGN_CFG,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("k1", "k2")},
                {"op": "tick", "t": 500},
                {"op": "append", "t": 600, "file": "app.log", "data": lines("k3")},
                {"op": "response", "t": 700, "batch": 1, "status": 200},
                {"op": "end", "t": 800}]
    return s


# --------------------------------------------------------- held-out captures
def held_out():
    s = {}
    cfg = dict(BENIGN_CFG)

    # -- unterminated fragments (2.1) -------------------------------------
    s["h01"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": "one\ntwo\nthr"},
                {"op": "append", "t": 20, "file": "app.log", "data": "ee\nfour\n"},
                {"op": "response", "t": 30, "batch": 1, "status": 200},
                {"op": "end", "t": 40}]

    s["h02"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": "no newline at all"},
                {"op": "end", "t": 20}]

    # -- age-based flush (4.3) --------------------------------------------
    age = dict(cfg, max_age_ms=1000)
    s["h03"] = [age,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("slow1", "slow2")},
                {"op": "tick", "t": 1010},
                {"op": "response", "t": 1020, "batch": 1, "status": 200},
                {"op": "end", "t": 1030}]

    s["h04"] = [age,
                {"op": "append", "t": 0, "file": "app.log", "data": lines("only")},
                {"op": "tick", "t": 999},
                {"op": "tick", "t": 1000},
                {"op": "response", "t": 1100, "batch": 1, "status": 200},
                {"op": "end", "t": 1200}]

    # -- byte-based flush (4.2) -------------------------------------------
    tight = dict(cfg, max_lines=10, max_bytes=20)
    s["h05"] = [tight,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("aaaaaaaa", "bbbbbbbb")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "end", "t": 30}]

    s["h06"] = [tight,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("a" * 25)},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "end", "t": 30}]

    # -- rotation with pending lines and a fragment (3.1-3.3) --------------
    hold = dict(cfg, max_lines=5)
    s["h07"] = [hold,
                {"op": "append", "t": 10, "file": "app.log", "data": "r1\nr2\nfrag"},
                {"op": "rotate", "t": 20, "file": "app.log"},
                {"op": "append", "t": 30, "file": "app.log", "data": lines("n1", "n2", "n3")},
                {"op": "response", "t": 40, "batch": 1, "status": 200},
                {"op": "end", "t": 50}]

    s["h08"] = [hold,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("keep1", "keep2")},
                {"op": "rotate", "t": 20, "file": "app.log"},
                {"op": "append", "t": 30, "file": "app.log", "data": lines("new1", "new2", "new3")},
                {"op": "response", "t": 40, "batch": 1, "status": 200},
                {"op": "end", "t": 50}]

    # -- transient failure and front requeue (5.2) ------------------------
    s["h09"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("f1", "f2", "f3")},
                {"op": "append", "t": 20, "file": "app.log", "data": lines("g1", "g2", "g3")},
                {"op": "response", "t": 30, "batch": 1, "status": 503},
                {"op": "response", "t": 40, "batch": 2, "status": 200},
                {"op": "response", "t": 50, "batch": 3, "status": 200},
                {"op": "end", "t": 60}]

    s["h10"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("A", "B", "C")},
                {"op": "response", "t": 20, "batch": 1, "status": 500},
                {"op": "append", "t": 30, "file": "app.log", "data": lines("D")},
                {"op": "response", "t": 40, "batch": 2, "status": 200},
                {"op": "end", "t": 50}]

    # -- retry exhaustion (5.3) -------------------------------------------
    once = dict(cfg, max_retries=1)
    s["h11"] = [once,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("z1", "z2", "z3")},
                {"op": "response", "t": 20, "batch": 1, "status": 502},
                {"op": "end", "t": 30}]

    twice = dict(cfg, max_retries=2)
    s["h12"] = [twice,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("y1", "y2", "y3")},
                {"op": "response", "t": 20, "batch": 1, "status": 503},
                {"op": "response", "t": 30, "batch": 2, "status": 503},
                {"op": "end", "t": 40}]

    # -- permanent rejection (5.4) ----------------------------------------
    s["h13"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("bad1", "bad2", "bad3")},
                {"op": "response", "t": 20, "batch": 1, "status": 413},
                {"op": "end", "t": 30}]

    s["h14"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("c1", "c2", "c3")},
                {"op": "response", "t": 20, "batch": 1, "status": 503},
                {"op": "response", "t": 30, "batch": 2, "status": 422},
                {"op": "end", "t": 40}]

    # -- stale / unknown batch ids (5.5) ----------------------------------
    s["h15"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("s1", "s2", "s3")},
                {"op": "response", "t": 20, "batch": 99, "status": 200},
                {"op": "response", "t": 30, "batch": 1, "status": 200},
                {"op": "response", "t": 40, "batch": 1, "status": 200},
                {"op": "end", "t": 50}]

    # -- backpressure drops the oldest (6.1-6.3) --------------------------
    small = dict(cfg, max_lines=100, max_bytes=100000, spool_max_bytes=12)
    s["h16"] = [small,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("dd1", "dd2", "dd3", "dd4")},
                {"op": "end", "t": 20}]

    s["h17"] = [dict(small, spool_max_bytes=8),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("ee1", "ee2")},
                {"op": "append", "t": 20, "file": "app.log", "data": lines("ee3")},
                {"op": "end", "t": 30}]

    # requeued lines can themselves be dropped (6.3)
    s["h18"] = [dict(cfg, max_lines=2, spool_max_bytes=12),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("q1", "q2")},
                {"op": "append", "t": 20, "file": "app.log", "data": lines("q3", "q4")},
                {"op": "response", "t": 30, "batch": 1, "status": 503},
                {"op": "end", "t": 40}]

    # -- restart re-reads from the acked offset (7.1-7.3) -----------------
    s["h19"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("w1", "w2", "w3")},
                {"op": "restart", "t": 20},
                {"op": "append", "t": 30, "file": "app.log", "data": lines("w4")},
                {"op": "response", "t": 40, "batch": 2, "status": 200},
                {"op": "end", "t": 50}]

    s["h20"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("v1", "v2", "v3")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "append", "t": 30, "file": "app.log", "data": lines("v4", "v5")},
                {"op": "restart", "t": 40},
                {"op": "append", "t": 50, "file": "app.log", "data": lines("v6")},
                {"op": "response", "t": 60, "batch": 2, "status": 200},
                {"op": "end", "t": 70}]

    # a response for a batch lost to restart must be ignored
    s["h21"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("t1", "t2", "t3")},
                {"op": "restart", "t": 20},
                {"op": "response", "t": 30, "batch": 1, "status": 200},
                {"op": "end", "t": 40}]

    # -- out-of-order responses (5.1) -------------------------------------
    s["h22"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("o1", "o2", "o3", "o4", "o5", "o6")},
                {"op": "response", "t": 20, "batch": 2, "status": 200},
                {"op": "response", "t": 30, "batch": 1, "status": 200},
                {"op": "end", "t": 40}]

    # -- several batches from one event (4.4) -----------------------------
    s["h23"] = [dict(cfg, max_lines=2),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("b1", "b2", "b3", "b4", "b5")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "response", "t": 21, "batch": 2, "status": 200},
                {"op": "end", "t": 30}]

    # -- multi-file offsets and interleaving ------------------------------
    s["h24"] = [dict(cfg, max_lines=4),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("i1", "i2")},
                {"op": "append", "t": 20, "file": "audit.log", "data": lines("j1", "j2")},
                {"op": "response", "t": 30, "batch": 1, "status": 200},
                {"op": "end", "t": 40}]

    s["h25"] = [dict(cfg, max_lines=4),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("k1", "k2")},
                {"op": "append", "t": 20, "file": "audit.log", "data": lines("l1", "l2")},
                {"op": "response", "t": 30, "batch": 1, "status": 503},
                {"op": "response", "t": 40, "batch": 2, "status": 200},
                {"op": "end", "t": 50}]

    # -- unicode line lengths are counted in bytes (4.2) ------------------
    s["h26"] = [dict(cfg, max_lines=10, max_bytes=16),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("ééé", "ééé")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "end", "t": 30}]

    # -- rotation then ack of pre-rotation lines (3.3) --------------------
    s["h27"] = [dict(cfg, max_lines=2),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("g1", "g2")},
                {"op": "rotate", "t": 20, "file": "app.log"},
                {"op": "append", "t": 30, "file": "app.log", "data": lines("h1")},
                {"op": "response", "t": 40, "batch": 1, "status": 200},
                {"op": "end", "t": 50}]

    # -- age measured from the oldest line, not the newest ----------------
    s["h28"] = [dict(cfg, max_lines=5, max_age_ms=100),
                {"op": "append", "t": 0, "file": "app.log", "data": lines("old")},
                {"op": "append", "t": 60, "file": "app.log", "data": lines("mid")},
                {"op": "tick", "t": 110},
                {"op": "response", "t": 120, "batch": 1, "status": 200},
                {"op": "end", "t": 130}]

    # -- empty lines are still lines --------------------------------------
    s["h29"] = [dict(cfg, max_lines=3),
                {"op": "append", "t": 10, "file": "app.log", "data": "\n\n\n"},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "end", "t": 30}]

    # -- no flush at end of session (8.1) ---------------------------------
    s["h30"] = [dict(cfg, max_lines=5),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("left1", "left2")},
                {"op": "end", "t": 20}]

    # -- requeue goes to the FRONT, ahead of lines that arrived meanwhile (5.2)
    s["h31"] = [cfg,
                {"op": "append", "t": 10, "file": "app.log", "data": lines("f1", "f2", "f3")},
                {"op": "append", "t": 20, "file": "app.log", "data": lines("p1", "p2")},
                {"op": "response", "t": 30, "batch": 1, "status": 503},
                {"op": "response", "t": 40, "batch": 2, "status": 200},
                {"op": "end", "t": 50}]

    # -- dead-letter strictly above max_retries, not at it (5.3) -----------
    s["h32"] = [dict(cfg, max_retries=2),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("r1", "r2", "r3")},
                {"op": "response", "t": 20, "batch": 1, "status": 503},
                {"op": "end", "t": 30}]

    # -- flush threshold counted in UTF-8 bytes, not characters (4.2) ------
    s["h33"] = [dict(cfg, max_lines=10, max_bytes=14),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("ééé", "ééé")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "end", "t": 30}]

    # -- requeued lines are themselves subject to backpressure (6.3) -------
    s["h34"] = [dict(cfg, max_lines=2, spool_max_bytes=8),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("aa", "bb")},
                {"op": "append", "t": 20, "file": "app.log", "data": lines("cc")},
                {"op": "response", "t": 30, "batch": 1, "status": 503},
                {"op": "end", "t": 40}]

    # -- backpressure keeps the newest, drops the oldest, and it shows -----
    s["h35"] = [dict(cfg, max_lines=3, spool_max_bytes=9),
                {"op": "append", "t": 10, "file": "app.log", "data": lines("n1", "n2", "n3", "n4")},
                {"op": "response", "t": 20, "batch": 1, "status": 200},
                {"op": "end", "t": 30}]

    return s


def write(target, sessions):
    target.mkdir(parents=True, exist_ok=True)
    for name, recs in sorted(sessions.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in recs)
        (target / (name + ".session")).write_text(text, encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".session")).read_text(encoding="utf-8")
        expected[name] = reference_shipper.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
