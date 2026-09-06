#!/usr/bin/env python3
"""Regenerate the sample and held-out session corpora, and samples/expected.json.

  samples/          Six sessions from a backfill that went smoothly: a range that
                    divides evenly into chunks, every attempt succeeding, the
                    rate limit never reached, no pause, no resume point and a
                    percentage that comes out whole. Almost every plausible
                    reading of the specification reproduces expected.json here.

  tests/sessions/   Held-out sessions covering the rest: a short final chunk, a
                    resume point below and above the range, failures and the
                    halt they lead to, the failure count resetting, the sliding
                    window at its boundary, waits, pausing and resuming, a
                    halted job that will not restart, an empty range and a
                    percentage that has to be floored - and then the three
                    families the visible samples say nothing about at all:
                    b*  captures stitched across process restarts
                    p*  control-table retunes while a chunk is in flight
                    c*  boot records whose reported checkpoint is a stale read

  environment/incidents/
                    The one capture that ships with the answer beside it: the
                    inc-4712 session and the gateway's own attempt log for the
                    same job. Between them they pin every rule the visible
                    samples leave open.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_backfill  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"
INCIDENTS = ROOT / "environment" / "incidents"


def config(start=0, end=300, chunk_size=100, max_attempts=3,
           max_chunks_per_window=10, window_seconds=60, outcomes=None,
           resume_from=None):
    record = {"op": "config", "start": start, "end": end,
              "chunk_size": chunk_size, "max_attempts": max_attempts,
              "max_chunks_per_window": max_chunks_per_window,
              "window_seconds": window_seconds}
    if outcomes is not None:
        record["outcomes"] = outcomes
    if resume_from is not None:
        record["resume_from"] = resume_from
    return record


def attempt(t):
    return {"op": "attempt", "t": t}


def pause(t):
    return {"op": "pause", "t": t}


def resume(t):
    return {"op": "resume", "t": t}


def tick(t):
    return {"op": "tick", "t": t}


def end(t):
    return {"op": "end", "t": t}


def boot(t, at, cp):
    return {"op": "boot", "t": t, "at": at, "cp": cp}


def policy(t, **fields):
    record = {"op": "policy", "t": t}
    record.update(fields)
    return record


def attempts(*times):
    return [attempt(t) for t in times]


# ------------------------------------------------------------ benign samples
def benign():
    # The range always divides evenly, every attempt succeeds, the rate limit is
    # far out of reach, nothing pauses and no resume point is given. Every
    # attempt is covered by an explicit outcome, so nothing ever reads past the
    # end of the list, and every final percentage is exact, so rounding and
    # flooring agree. The short final chunk, the failure path, the window, the
    # pause flag, the exhausted outcome list and the floored percentage are all
    # settled only by the held-out corpus.
    ok3 = ["ok", "ok", "ok"]
    s = {}
    s["s01"] = [config(outcomes=ok3), *attempts(10, 20, 30), end(100)]
    s["s02"] = [config(end=100, outcomes=["ok"]), *attempts(10), end(100)]
    s["s03"] = [config(end=200, outcomes=["ok"]), *attempts(10), end(100)]
    s["s04"] = [config(end=200, chunk_size=50, outcomes=ok3 + ["ok"]),
                *attempts(10, 20, 30, 40), end(100)]
    s["s05"] = [config(outcomes=ok3), *attempts(10, 20, 30, 40, 50), end(100)]
    s["s06"] = [config(start=1000, end=1300, outcomes=ok3),
                *attempts(10, 20, 30), end(100)]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- the final chunk is short (1.3) -------------------------------------
    s["h01"] = [config(end=250), *attempts(10, 20, 30), end(100)]
    s["h02"] = [config(end=50), *attempts(10), end(100)]
    s["h03"] = [config(start=5, end=255), *attempts(10, 20, 30), end(100)]

    # -- a resume point (2.1, 2.2) ------------------------------------------
    s["h04"] = [config(resume_from=100), *attempts(10, 20), end(100)]
    s["h05"] = [config(resume_from=-50), *attempts(10, 20, 30), end(100)]
    s["h06"] = [config(resume_from=300), *attempts(10, 20), end(100)]
    s["h07"] = [config(resume_from=350), *attempts(10), end(100)]
    s["h08"] = [config(resume_from=150), *attempts(10, 20), end(100)]

    # -- an empty range never attempts anything (1.4, 6.2, 6.3) -------------
    s["h09"] = [config(start=100, end=100), *attempts(10, 20), end(100)]
    s["h10"] = [config(start=100, end=50), *attempts(10), end(100)]

    # -- a failure leaves the checkpoint alone and retries (2.3, 4.3) -------
    s["h11"] = [config(outcomes=["fail", "ok"]), *attempts(10, 20, 30, 40), end(100)]
    s["h12"] = [config(outcomes=["ok", "fail", "fail", "ok"]),
                *attempts(10, 20, 30, 40, 50), end(100)]

    # -- the failure count resets after a success (4.5) ---------------------
    s["h13"] = [config(max_attempts=2, outcomes=["fail", "ok", "fail", "ok"]),
                *attempts(10, 20, 30, 40, 50, 60), end(100)]

    # -- enough failures halt the job (4.4) ---------------------------------
    s["h14"] = [config(max_attempts=2, outcomes=["fail", "fail"]),
                *attempts(10, 20, 30, 40), end(100)]
    s["h15"] = [config(max_attempts=1, outcomes=["fail"]),
                *attempts(10, 20), end(100)]
    s["h16"] = [config(max_attempts=3, outcomes=["ok", "fail", "fail", "fail"]),
                *attempts(10, 20, 30, 40, 50), end(100)]

    # -- a halted job stays halted, even after resume (5.3) -----------------
    s["h17"] = [config(max_attempts=1, outcomes=["fail"]),
                attempt(10), pause(20), resume(30), *attempts(40, 50), end(100)]

    # -- the sliding window at its boundary (3.1) ---------------------------
    s["h18"] = [config(max_chunks_per_window=1, window_seconds=60),
                attempt(0), attempt(59), end(100)]
    s["h19"] = [config(max_chunks_per_window=1, window_seconds=60),
                attempt(0), attempt(60), end(100)]
    s["h20"] = [config(max_chunks_per_window=2, window_seconds=60),
                attempt(0), attempt(10), attempt(20), attempt(70), end(100)]

    # -- a wait is counted and the chunk is not skipped (3.3) ---------------
    s["h21"] = [config(max_chunks_per_window=1, window_seconds=100),
                attempt(0), attempt(10), attempt(20), attempt(200), end(300)]

    # -- a failed attempt still counts against the rate (3.2) ---------------
    s["h22"] = [config(max_chunks_per_window=2, window_seconds=60,
                       outcomes=["fail", "ok"]),
                attempt(0), attempt(10), attempt(20), attempt(70), end(100)]

    # -- pausing and resuming (5.1, 5.2) ------------------------------------
    s["h23"] = [config(), attempt(10), pause(20), *attempts(30, 40),
                resume(50), *attempts(60, 70), end(100)]
    # A pause between two failures: if pausing forgave the first one, the second
    # would not reach the limit and the job would not halt.
    s["h24"] = [config(max_attempts=2, outcomes=["fail", "fail"]),
                attempt(10), pause(20), resume(30), *attempts(40, 50), end(100)]

    # -- attempts after the job finishes do nothing -------------------------
    s["h25"] = [config(end=100), *attempts(10, 20, 30), end(100)]

    # -- the percentage is floored (6.3) ------------------------------------
    s["h26"] = [config(end=300, chunk_size=100), *attempts(10), end(100)]
    s["h27"] = [config(end=700, chunk_size=100), *attempts(10, 20), end(100)]
    s["h28"] = [config(end=300, chunk_size=70), *attempts(10), end(100)]

    # -- the outcomes list runs out and everything after it succeeds (4.1) --
    s["h29"] = [config(outcomes=["fail"]), *attempts(10, 20, 30, 40), end(100)]

    # -- a rate limit and a failure together --------------------------------
    s["h30"] = [config(max_chunks_per_window=1, window_seconds=50,
                       max_attempts=2, outcomes=["fail", "fail"]),
                attempt(0), attempt(10), attempt(60), attempt(120), end(200)]

    # == b*: the capture is stitched from several runner processes ==========
    # Each segment stamps t from its own process start, so only at + t spans
    # the file. What a boot keeps is the durability table in runner-internals.

    # the window is the gateway's, so it spans the boot, and only absolute
    # time makes the second segment's attempt admissible
    s["b01"] = [config(end=1000, max_chunks_per_window=2, window_seconds=60),
                boot(0, 0, 0), attempt(0), attempt(10),
                boot(0, 100, 200), attempt(0), end(50)]

    # ... and a boot does not empty it: absolute 30 is still inside
    s["b02"] = [config(end=1000, max_chunks_per_window=1, window_seconds=60),
                boot(0, 0, 0), attempt(0),
                boot(0, 30, 100), attempt(0), attempt(40), end(80)]

    # consecutive_failures is process memory, so a crash loop never halts
    s["b03"] = [config(end=1000, max_attempts=2, outcomes=["fail", "fail"]),
                boot(0, 0, 0), attempt(0),
                boot(0, 100, 0), attempt(0),
                boot(0, 200, 0), attempt(0), end(10)]

    # halted is in the job row, so it does survive
    s["b04"] = [config(end=1000, max_attempts=1, outcomes=["fail"]),
                boot(0, 0, 0), attempt(0),
                boot(0, 100, 0), attempt(0), attempt(10), end(20)]

    # and so does paused
    s["b05"] = [config(end=1000), boot(0, 0, 0), attempt(0), pause(10),
                boot(0, 100, 100), attempt(0), attempt(10), resume(20),
                attempt(30), end(40)]

    # a pause that outlives the process that set it
    s["b06"] = [config(end=1000), boot(0, 0, 0), attempt(0), pause(10),
                boot(0, 200, 100), attempt(0), attempt(10), end(20)]

    # the in-flight range is process memory too: the boot drops it, so the
    # retry is recomputed at the width the retune left behind
    s["b07"] = [config(end=1000, max_attempts=5, outcomes=["fail"]),
                boot(0, 0, 0), attempt(0), policy(10, chunk_size=40),
                boot(0, 100, 0), attempt(0), attempt(10), end(20)]

    # a segment whose clock is nowhere near the wall clock
    s["b08"] = [config(end=300), boot(0, 5000, 0),
                *attempts(0, 10, 20), end(30)]

    # a window that spans the boot and turns one attempt away
    s["b09"] = [config(end=1000, max_chunks_per_window=3, window_seconds=100),
                boot(0, 0, 0), *attempts(0, 10, 20),
                boot(0, 50, 300), attempt(0), attempt(60), end(70)]

    # == p*: the control table is retuned while the job runs ================

    # the canonical case: a chunk that failed is retried over the range it
    # already materialised, and only the next fresh chunk takes the new width
    s["p01"] = [config(end=1000, outcomes=["fail", "ok"]),
                attempt(0), policy(10, chunk_size=40),
                attempt(20), attempt(30), end(40)]

    # a retune is not a restart of the plan
    s["p02"] = [config(end=500), attempt(0), policy(10, chunk_size=250),
                attempt(20), attempt(30), end(40)]

    # raising the rate limit
    s["p03"] = [config(end=1000, max_chunks_per_window=1, window_seconds=60),
                attempt(0), attempt(10), policy(20, max_chunks_per_window=3),
                attempt(30), attempt(40), attempt(50), end(60)]

    # shortening the window
    s["p04"] = [config(end=1000, max_chunks_per_window=1, window_seconds=100),
                attempt(0), attempt(50), policy(60, window_seconds=30),
                attempt(70), end(80)]

    # a retune in the middle of the retries that halt the job
    s["p05"] = [config(end=1000, max_attempts=3,
                       outcomes=["fail", "fail", "fail"]),
                attempt(0), policy(10, chunk_size=30),
                attempt(20), attempt(30), attempt(40), end(50)]

    # the chunk in flight is the short final one
    s["p06"] = [config(start=100, end=430, chunk_size=200,
                       outcomes=["ok", "fail", "ok", "ok"]),
                attempt(0), attempt(10), policy(20, chunk_size=50),
                attempt(30), attempt(40), end(50)]

    # == c*: the checkpoint a boot reports is a replica read ================

    # cp lags a commit the dead process had already made
    s["c01"] = [config(end=1000), boot(0, 0, 0), *attempts(0, 10, 20),
                boot(0, 100, 200), attempt(0), end(10)]

    # cp is ahead: the collector missed a stretch the job did not
    s["c02"] = [config(end=1000), boot(0, 0, 0), attempt(0),
                boot(0, 500, 600), attempt(0), attempt(10), end(20)]

    # cp is past the end of the range
    s["c03"] = [config(end=300), boot(0, 0, 0), attempt(0),
                boot(0, 50, 300), attempt(0), attempt(10), end(20)]

    # cp below the start of the range, and then a lagging one
    s["c04"] = [config(start=200, end=800), boot(0, 0, 0), attempt(0),
                boot(0, 100, 150), attempt(0), end(10)]

    # a lagging cp on a chunk that had failed just before the crash
    s["c05"] = [config(end=1000, max_attempts=3, outcomes=["ok", "fail"]),
                boot(0, 0, 0), attempt(0), attempt(10),
                boot(0, 100, 0), attempt(0), end(10)]
    return s


# ------------------------------------------------------------ the incident
def incident():
    """inc-4712: the capture that ships with the gateway's attempt log beside
    it. One job, eight runner processes, one mid-flight retune, one crash loop
    that never halts, one lagging boot and one boot that is ahead because the
    collector was down."""
    return [
        {"op": "config", "format": 3, "start": 0, "end": 1000,
         "chunk_size": 100, "max_attempts": 3, "max_chunks_per_window": 10,
         "window_seconds": 60,
         "outcomes": ["fail", "ok", "ok", "fail", "fail", "fail", "fail",
                      "fail"]},

        boot(0, 600, 0),
        attempt(0),                          # [0,100) fail
        policy(10, chunk_size=40),           # operator drops the width
        attempt(20),                         # still [0,100): already in flight
        attempt(30),                         # [100,140): the new width
        attempt(40),                         # [140,180) fail

        boot(0, 700, 140),                   # in-flight range dies with the process
        policy(5, chunk_size=60),
        attempt(10),                         # [140,200) fail

        boot(0, 800, 140),
        attempt(10),                         # [140,200) fail
        boot(0, 900, 140),
        attempt(10),                         # [140,200) fail
        boot(0, 1000, 140),
        attempt(10),                         # [140,200) fail - the fourth in a row
        attempt(20),                         # [140,200) ok at last
        policy(25, chunk_size=100),
        attempt(30),                         # [200,300) ok

        boot(0, 1100, 200),                  # replica lag: the row already said 300
        attempt(10),                         # [300,400) ok

        boot(0, 1200, 600),                  # collector gap: the row really said 600
        attempt(10),                         # [600,700) ok
        pause(20),
        attempt(30),                         # paused: no attempt, and no wait
        resume(40),
        attempt(50),                         # [700,800) ok
        policy(55, max_chunks_per_window=1, window_seconds=5),
        attempt(60),                         # [800,900) ok
        attempt(62),                         # throttled
        end(70),
    ]


def write(target, sessions):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(sessions.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".session")).write_text(text, encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())
    write(INCIDENTS, {"inc-4712": incident()})

    log = reference_backfill.replay_text(
        (INCIDENTS / "inc-4712.session").read_text(encoding="utf-8"))
    (INCIDENTS / "inc-4712-attempts.json").write_text(
        json.dumps({
            "incident": "INC-4712",
            "job": "orders.enriched_at backfill",
            "source": "api-gateway chunk-attempt log, exported 2026-03-14",
            "note": ("Every chunk attempt the gateway saw for this job, in "
                     "order. t is the wall-second: the gateway has one clock "
                     "and does not care which runner process was asking. "
                     "throttle_events is how many requests it refused for "
                     "rate. The gateway never sees an attempt the runner "
                     "decided not to make."),
            "attempts": log["attempts"],
            "throttle_events": log["waits"],
            "final_checkpoint": log["state"]["checkpoint"],
            "halted": log["state"]["halted"],
        }, indent=2) + "\n", encoding="utf-8", newline="\n")

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".session")).read_text(encoding="utf-8")
        expected[name] = reference_backfill.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("incident : inc-4712 (%d attempts)" % len(log["attempts"]))
    print("expected.json written")


if __name__ == "__main__":
    main()
