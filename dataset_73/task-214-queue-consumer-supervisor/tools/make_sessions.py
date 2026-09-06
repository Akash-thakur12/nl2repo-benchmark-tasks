#!/usr/bin/env python3
"""Regenerate the sample and held-out session corpora, and samples/expected.json.

  samples/          Six sessions from a fleet that behaves: one worker,
                    heartbeats comfortably inside the timeout, no crashes, no
                    work in hand, no draining and nothing unknown. Almost every
                    plausible reading of the specification reproduces
                    expected.json here.

  tests/sessions/   Held-out sessions covering the rest: the heartbeat boundary,
                    crashes and the backoff table, the consecutive count and
                    when it resets, the crash-loop limit and its window,
                    draining with and without work in hand, a drain that a crash
                    interrupts, and records naming a worker nobody configured.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_supervisor  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"


def config(workers=None, backoff_ms=None, reset_after_ms=60000,
           heartbeat_timeout_ms=30000, max_restarts=3, restart_window_ms=300000):
    return {"op": "config", "workers": list(workers or ["a"]),
            "backoff_ms": list(backoff_ms or [1000, 5000]),
            "reset_after_ms": reset_after_ms,
            "heartbeat_timeout_ms": heartbeat_timeout_ms,
            "max_restarts": max_restarts,
            "restart_window_ms": restart_window_ms}


def beat(t, worker="a"):
    return {"op": "heartbeat", "t": t, "worker": worker}


def crash(t, worker="a"):
    return {"op": "crash", "t": t, "worker": worker}


def work(t, worker="a"):
    return {"op": "work", "t": t, "worker": worker}


def finished(t, worker="a"):
    return {"op": "finished", "t": t, "worker": worker}


def drain(t, worker="a"):
    return {"op": "drain", "t": t, "worker": worker}


def tick(t):
    return {"op": "tick", "t": t}


def end(t):
    return {"op": "end", "t": t}


def beats(*times, **kw):
    return [beat(t, kw.get("worker", "a")) for t in times]


# ------------------------------------------------------------ benign samples
def benign():
    # One worker, heartbeats well inside the timeout, nothing ever crashes,
    # nothing is ever draining and no worker has work in hand. The timeout
    # boundary, the backoff table, the crash-loop limit and every drain rule are
    # settled by the held-out corpus.
    s = {}
    s["s01"] = [config(), *beats(1000, 2000, 3000), end(4000)]
    s["s02"] = [config(), *beats(10000, 20000, 30000), end(40000)]
    s["s03"] = [config(), beat(1000), tick(2000), beat(3000), end(4000)]
    s["s04"] = [config(workers=["a", "b"]), beat(1000, "a"), beat(1000, "b"),
                beat(2000, "a"), beat(2000, "b"), end(3000)]
    s["s05"] = [config(), *beats(5000, 10000, 15000, 20000), end(25000)]
    s["s06"] = [config(), end(1000)]
    s["s07"] = [config(workers=["ingest", "notify", "verify"],
                       heartbeat_timeout_ms=15000),
                *[beat(t, w) for t in (5000, 10000, 15000, 20000)
                  for w in ("ingest", "notify", "verify")],
                tick(25000), end(30000)]
    s["s08"] = [config(workers=["primary", "replica"], backoff_ms=[250, 1000, 4000],
                       heartbeat_timeout_ms=8000, reset_after_ms=20000,
                       max_restarts=5, restart_window_ms=120000),
                beat(2000, "primary"), beat(3000, "replica"),
                tick(4000),
                beat(9000, "primary"), beat(9500, "replica"),
                tick(12000),
                beat(16000, "primary"), beat(16000, "replica"),
                end(20000)]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- the heartbeat timeout is strictly greater (2.1) --------------------
    s["h01"] = [config(), tick(30000), end(40000)]
    s["h02"] = [config(), tick(30001), end(40000)]
    s["h03"] = [config(), beat(10000), tick(40000), end(50000)]
    s["h04"] = [config(), beat(10000), tick(40001), end(50000)]

    # -- an unhealthy worker crashes and is restarted (2.3, 3.5) ------------
    s["h05"] = [config(), tick(30001), tick(31001), end(40000)]
    s["h06"] = [config(), tick(30001), tick(31000), tick(31001), end(40000)]

    # -- the backoff table advances with consecutive restarts (3.4) ---------
    s["h07"] = [config(backoff_ms=[1000, 5000, 20000], reset_after_ms=1000000,
                       max_restarts=9),
                crash(1000), tick(2000),
                crash(3000), tick(8000),
                crash(9000), tick(29000),
                crash(30000), tick(40000), tick(60000), end(70000)]

    # -- past the end of the table the last entry repeats (3.4) -------------
    s["h08"] = [config(backoff_ms=[1000], reset_after_ms=1000000, max_restarts=9),
                crash(1000), tick(2000), crash(3000), tick(4000),
                crash(5000), tick(6000), end(10000)]

    # -- a restart is due at exactly its time (3.5) -------------------------
    s["h09"] = [config(), crash(1000), tick(1999), tick(2000), end(3000)]

    # -- the consecutive count resets after a healthy spell (3.6) -----------
    s["h10"] = [config(backoff_ms=[1000, 5000], reset_after_ms=10000,
                       heartbeat_timeout_ms=100000),
                crash(1000), tick(2000),
                tick(13000),
                crash(14000), tick(15000), end(20000)]

    s["h11"] = [config(backoff_ms=[1000, 5000], reset_after_ms=10000,
                       heartbeat_timeout_ms=100000),
                crash(1000), tick(2000),
                crash(5000), tick(11000), end(20000)]

    # -- the crash-loop limit (3.3) -----------------------------------------
    s["h12"] = [config(backoff_ms=[100], max_restarts=2, reset_after_ms=1000000),
                crash(1000), tick(1100), crash(1200), tick(1300),
                crash(1400), tick(1500), end(2000)]

    s["h13"] = [config(backoff_ms=[100], max_restarts=0, reset_after_ms=1000000),
                crash(1000), tick(2000), end(3000)]

    # -- crashes outside the window do not count toward the limit (3.3) -----
    s["h14"] = [config(backoff_ms=[100], max_restarts=1, restart_window_ms=1000,
                       reset_after_ms=1000000),
                crash(1000), tick(1100),
                crash(5000), tick(5100),
                crash(9000), tick(9100), end(10000)]

    # -- a failed worker is never touched again (3.3) -----------------------
    s["h15"] = [config(backoff_ms=[100], max_restarts=0, reset_after_ms=1000000),
                crash(1000), tick(2000), beat(3000), crash(4000), drain(5000),
                tick(100000), end(200000)]

    # -- work in hand, and a drain that waits for it (4, 5.1, 5.2) ----------
    s["h16"] = [config(heartbeat_timeout_ms=1000000),
                work(1000), drain(2000), tick(3000), finished(4000),
                tick(5000), end(6000)]

    s["h17"] = [config(heartbeat_timeout_ms=1000000),
                drain(2000), tick(3000), end(4000)]

    s["h18"] = [config(heartbeat_timeout_ms=1000000),
                work(1000), finished(1500), drain(2000), end(3000)]

    # -- a crash takes the work away (4.3) ----------------------------------
    s["h19"] = [config(heartbeat_timeout_ms=1000000, reset_after_ms=1000000),
                work(1000), crash(2000), tick(3000),
                drain(4000), tick(5000), end(6000)]

    # -- a draining worker is still checked for health (5.3) ----------------
    s["h20"] = [config(heartbeat_timeout_ms=1000),
                beat(500), work(600), drain(700), tick(1600), tick(2700),
                end(5000)]

    # -- a draining worker that crashes stops draining (5.3) ----------------
    s["h21"] = [config(heartbeat_timeout_ms=1000000, reset_after_ms=1000000),
                work(1000), drain(2000), crash(3000), tick(4000),
                finished(5000), end(6000)]

    # -- a stopped worker is never restarted or drained again (5.4, 5.5) ----
    s["h22"] = [config(heartbeat_timeout_ms=1000),
                drain(500), tick(5000), drain(6000), crash(7000),
                tick(100000), end(200000)]

    # -- draining a worker that is down is ignored (5.5) --------------------
    s["h23"] = [config(backoff_ms=[100000], heartbeat_timeout_ms=1000000),
                crash(1000), drain(2000), tick(3000), end(4000)]

    # -- a heartbeat from a worker that is not running is ignored (2.4) -----
    s["h24"] = [config(backoff_ms=[100000], heartbeat_timeout_ms=1000000),
                crash(1000), beat(2000), tick(3000), end(4000)]

    # -- workers are visited in configuration order (2.2) -------------------
    s["h25"] = [config(workers=["zebra", "alpha"], heartbeat_timeout_ms=1000),
                tick(1001), end(5000)]

    s["h26"] = [config(workers=["a", "b"], heartbeat_timeout_ms=1000),
                beat(500, "a"), tick(1001), tick(2002), end(5000)]

    # -- an unknown worker (1.3) ---------------------------------------------
    s["h27"] = [config(heartbeat_timeout_ms=1000000),
                beat(1000, "ghost"), crash(2000, "ghost"), drain(3000, "ghost"),
                work(4000, "ghost"), end(5000)]

    # -- a restart sets the last heartbeat (3.5) ----------------------------
    s["h28"] = [config(backoff_ms=[1000], heartbeat_timeout_ms=500,
                       reset_after_ms=1000000, max_restarts=9),
                crash(1000), tick(2000), end(3000)]

    # -- two workers, independent of one another ----------------------------
    s["h29"] = [config(workers=["a", "b"], heartbeat_timeout_ms=1000000,
                       reset_after_ms=1000000),
                crash(1000, "a"), tick(2000), crash(3000, "b"), tick(4000),
                end(5000)]

    # -- everything at once ---------------------------------------------------
    s["h30"] = [config(workers=["a", "b"], backoff_ms=[500, 2000],
                       heartbeat_timeout_ms=2000, reset_after_ms=10000,
                       max_restarts=2, restart_window_ms=10000),
                beat(1000, "a"), beat(1000, "b"),
                work(1500, "a"), drain(1600, "a"),
                crash(1800, "b"), tick(2300),
                finished(2500, "a"),
                tick(4600), tick(7000), end(12000)]
    # -- a crash exactly one window old still counts (3.3) ------------------
    s["h31"] = [config(backoff_ms=[100], max_restarts=1, restart_window_ms=1000,
                       reset_after_ms=1000000, heartbeat_timeout_ms=1000000),
                crash(1000), tick(1100), crash(2000), tick(2100), end(3000)]

    # -- the consecutive count resets at exactly reset_after_ms (3.6) --------
    s["h32"] = [config(backoff_ms=[1000, 5000], reset_after_ms=10000,
                       heartbeat_timeout_ms=1000000, max_restarts=9),
                crash(1000), tick(2000), tick(12000),
                crash(13000), tick(15000), end(20000)]

    # -- the reset is measured from the start, not the last heartbeat (3.6) --
    s["h33"] = [config(backoff_ms=[1000, 5000], reset_after_ms=10000,
                       heartbeat_timeout_ms=1000000, max_restarts=9),
                crash(1000), tick(2000), beat(8000), tick(12000),
                crash(13000), tick(15000), end(20000)]

    # -- the reset does not clear the restart history (3.6) -----------------
    s["h34"] = [config(backoff_ms=[100], max_restarts=1, restart_window_ms=1000000,
                       reset_after_ms=5000, heartbeat_timeout_ms=1000000),
                crash(1000), tick(1100), tick(7000), crash(8000),
                tick(9000), end(10000)]

    # -- the reset clock starts again at every restart (3.5, 3.6) -----------
    s["h35"] = [config(backoff_ms=[500, 9000], reset_after_ms=20000,
                       heartbeat_timeout_ms=1000000, max_restarts=9),
                crash(1000), tick(2000), tick(19000), tick(21000),
                crash(22000), tick(22600), end(40000)]
    return s


def write(target, sessions):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(sessions.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".session")).write_text(text, encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".session")).read_text(encoding="utf-8")
        expected[name] = reference_supervisor.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
