#!/usr/bin/env python3
"""Regenerate the sample and held-out session corpora, and samples/expected.json.

  samples/          Six sessions from a fleet with one environment, every
                    consumer registered before the rotation starts, every
                    acknowledgement arriving after its stage has begun, nothing
                    ever unhealthy, no dry runs, no second rotation and a grace
                    period that expires well clear of its boundary. Almost every
                    plausible reading of the specification reproduces
                    expected.json here.

  tests/sessions/   Held-out sessions covering the rest: several environments in
                    rollout order, environments with no consumers, early
                    acknowledgements, unknown consumers and environments,
                    rollback in reverse order, discarded acknowledgements,
                    version numbers that are never reused, dry runs, the grace
                    boundary, a second rotation cutting a grace period short,
                    records whose timestamps run backwards, mid-session policy
                    changes, and fleet membership changing during a rollout.

  environment/archive/  One capture from the live runner (rot-4417.session)
                    beside the runner's own log for that run
                    (rot-4417.runner.log). The log is generated from the
                    reference model here, so it cannot drift from ground truth.
                    It is the artifact that pins down the behaviours the
                    specification deliberately no longer spells out.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_rotation  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"
ARCHIVE = ROOT / "environment" / "archive"

ONE = ["prod"]
THREE = ["dev", "staging", "prod"]


def config(environments=None, grace_seconds=300):
    return {"op": "config", "environments": environments or ONE,
            "grace_seconds": grace_seconds}


def consumer(t, cid, env):
    return {"op": "consumer", "t": t, "id": cid, "env": env}


def health(t, env, ok):
    return {"op": "health", "t": t, "env": env, "ok": ok}


def rotate(t, dry_run=False):
    record = {"op": "rotate", "t": t}
    if dry_run:
        record["dry_run"] = True
    return record


def ack(t, cid, version):
    return {"op": "ack", "t": t, "consumer": cid, "version": version}


def policy(t, grace_seconds):
    return {"op": "policy", "t": t, "grace_seconds": grace_seconds}


def tick(t):
    return {"op": "tick", "t": t}


def end(t):
    return {"op": "end", "t": t}


# ------------------------------------------------------------ benign samples
def benign():
    s = {}

    # Every session here stops before its grace period expires, so revocation
    # never appears in the visible corpus, and every environment has a consumer,
    # so a runner that waits for an acknowledgement that will never come is not
    # caught here either. Both live in the held-out corpus.
    s["s01"] = [config(), consumer(10, "api", "prod"), rotate(100),
                ack(110, "api", 2), tick(200), end(300)]

    s["s02"] = [config(), consumer(10, "api", "prod"), consumer(20, "worker", "prod"),
                rotate(100), ack(110, "api", 2), ack(120, "worker", 2),
                tick(200), end(300)]

    s["s03"] = [config(), consumer(10, "api", "prod"), rotate(100),
                ack(110, "api", 2), end(200)]

    s["s04"] = [config(), consumer(10, "api", "prod"), rotate(100),
                ack(120, "api", 2), tick(150), end(200)]

    s["s05"] = [config(), consumer(10, "api", "prod"), rotate(100),
                ack(150, "api", 2), tick(300), end(400)]

    s["s06"] = [config(grace_seconds=600), consumer(10, "api", "prod"),
                rotate(100), ack(110, "api", 2), tick(500), end(600)]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- environments stage in rollout order (2.1, 6.2) --------------------
    s["h01"] = [config(THREE), consumer(10, "d", "dev"), consumer(11, "s", "staging"),
                consumer(12, "p", "prod"), rotate(100),
                ack(110, "d", 2), ack(120, "s", 2), ack(130, "p", 2),
                tick(900), end(1000)]

    # -- an environment with no consumers completes at once (6.1) ----------
    s["h02"] = [config(THREE), consumer(12, "p", "prod"), rotate(100),
                ack(110, "p", 2), tick(900), end(1000)]

    s["h03"] = [config(THREE), rotate(100), tick(900), end(1000)]

    # -- a stage waits for every consumer in it (6.1) ----------------------
    s["h04"] = [config(THREE), consumer(10, "d1", "dev"), consumer(11, "d2", "dev"),
                rotate(100), ack(110, "d1", 2), tick(200),
                ack(300, "d2", 2), tick(900), end(1000)]

    # -- an early acknowledgement still counts (5.2) -----------------------
    s["h05"] = [config(THREE), consumer(10, "d", "dev"), consumer(12, "p", "prod"),
                ack(50, "p", 2), rotate(100), ack(110, "d", 2),
                tick(900), end(1000)]

    # -- an acknowledgement for a version that never exists (5.3) ----------
    s["h06"] = [config(), consumer(10, "api", "prod"), ack(50, "api", 99),
                rotate(100), tick(900), end(1000)]

    # -- unknown consumer and unknown environment (2.3, 2.4, 5.1) ----------
    s["h07"] = [config(), ack(50, "ghost", 2), consumer(60, "api", "nowhere"),
                health(70, "nowhere", False), rotate(100), end(200)]

    # -- an unhealthy staging environment rolls back at once (7.1) ---------
    s["h08"] = [config(THREE), consumer(10, "d", "dev"),
                health(50, "dev", False), rotate(100), tick(900), end(1000)]

    # -- rollback names completed environments in reverse order (7.1) ------
    s["h09"] = [config(THREE), consumer(10, "d", "dev"), consumer(11, "s", "staging"),
                consumer(12, "p", "prod"), rotate(100),
                ack(110, "d", 2), ack(120, "s", 2),
                health(200, "prod", False), tick(900), end(1000)]

    # -- a rollback forgets that version's acknowledgements (7.2) ----------
    s["h10"] = [config(THREE), consumer(10, "d", "dev"), consumer(11, "s", "staging"),
                consumer(12, "p", "prod"),
                rotate(100), ack(110, "d", 2),
                health(200, "staging", False), tick(300),
                health(400, "staging", True), rotate(500),
                ack(510, "d", 3), ack(520, "s", 3), ack(530, "p", 3),
                tick(1500), end(1600)]

    # -- a version is never reused after a rollback (3.2, 7.2) -------------
    s["h11"] = [config(), consumer(10, "api", "prod"),
                health(50, "prod", False), rotate(100), tick(200),
                health(300, "prod", True), rotate(400), ack(410, "api", 3),
                tick(1200), end(1300)]

    # -- a rollback does not start a grace period (7.3) --------------------
    s["h12"] = [config(), consumer(10, "api", "prod"),
                health(50, "prod", False), rotate(100), tick(5000), end(6000)]

    # -- rotating while one is in flight (4.2) -----------------------------
    s["h13"] = [config(THREE), consumer(10, "d", "dev"), rotate(100),
                rotate(150), ack(200, "d", 2), tick(900), end(1000)]

    # -- a dry run changes nothing at all (4.1) ----------------------------
    s["h14"] = [config(), consumer(10, "api", "prod"), rotate(50, dry_run=True),
                rotate(100), ack(110, "api", 2), tick(900), end(1000)]

    s["h15"] = [config(THREE), rotate(50, dry_run=True), rotate(60, dry_run=True),
                end(100)]

    # -- a dry run during a rotation is still just a plan (4.1, 4.2) -------
    s["h16"] = [config(THREE), consumer(10, "d", "dev"), rotate(100),
                rotate(150, dry_run=True), ack(200, "d", 2), tick(900), end(1000)]

    # -- the grace boundary is inclusive (8.1) -----------------------------
    s["h17"] = [config(grace_seconds=100), consumer(10, "api", "prod"),
                rotate(100), ack(110, "api", 2), tick(209), tick(210), end(300)]

    s["h18"] = [config(grace_seconds=0), consumer(10, "api", "prod"),
                rotate(100), ack(110, "api", 2), end(200)]

    # -- a second rotation cuts a grace period short (8.3) -----------------
    s["h19"] = [config(grace_seconds=10000), consumer(10, "api", "prod"),
                rotate(100), ack(110, "api", 2),
                rotate(200), ack(210, "api", 3), tick(300), end(400)]

    # -- three rotations in a row ------------------------------------------
    s["h20"] = [config(grace_seconds=50), consumer(10, "api", "prod"),
                rotate(100), ack(110, "api", 2), tick(200),
                rotate(300), ack(310, "api", 3), tick(400),
                rotate(500), ack(510, "api", 4), tick(600), end(700)]

    # -- a consumer moved between environments keeps its acks (2.2) --------
    s["h21"] = [config(THREE), consumer(10, "c", "prod"), ack(50, "c", 2),
                consumer(60, "c", "dev"), rotate(100), tick(900), end(1000)]

    # -- health recovering mid-stage lets the rotation continue ------------
    s["h22"] = [config(THREE), consumer(10, "d", "dev"), consumer(12, "p", "prod"),
                health(50, "staging", False), rotate(100), ack(110, "d", 2),
                tick(200), health(300, "staging", True), rotate(400),
                ack(410, "d", 3), ack(420, "p", 3), tick(1400), end(1500)]

    # -- an unhealthy environment later in the order does not block early --
    s["h23"] = [config(THREE), consumer(10, "d", "dev"),
                health(50, "prod", False), rotate(100), ack(110, "d", 2),
                tick(900), end(1000)]

    # -- acks arriving before any consumer is registered (5.1) -------------
    s["h24"] = [config(), ack(10, "api", 2), consumer(20, "api", "prod"),
                rotate(100), tick(900), end(1000)]

    # -- a stage completing on the health record rather than the ack -------
    s["h25"] = [config(THREE), consumer(10, "d", "dev"),
                health(50, "dev", False), ack(60, "d", 2), rotate(100),
                tick(200), health(300, "dev", True), rotate(400),
                ack(410, "d", 3), tick(1400), end(1500)]

    # -- the clock is a high-water mark: a record behind it does not rewind ---
    # h26 diverges only in the stamp on complete / stage / rotated.
    s["h26"] = [config(THREE), consumer(10, "d", "dev"), rotate(100),
                tick(250), ack(180, "d", 2), tick(900), end(1000)]

    # h27 straddles a grace deadline: rewinding the clock revokes far too early.
    s["h27"] = [config(grace_seconds=100), consumer(10, "api", "prod"),
                rotate(100), tick(400), ack(200, "api", 2),
                tick(380), tick(460), end(500)]

    # h28 rewinds twice across a multi-environment rollout ending in rollback.
    s["h28"] = [config(THREE), consumer(10, "d", "dev"), consumer(11, "s", "staging"),
                consumer(12, "p", "prod"), rotate(100), tick(500),
                ack(200, "d", 2), ack(450, "s", 2),
                health(600, "prod", False), tick(900), end(1000)]

    # -- a grace period serves the window it was granted (8.0, 8.1) ---------
    # h29: the countdown started under 600s and keeps it; the event timestamp
    # differs from a runner that recomputes against the new policy.
    s["h29"] = [config(grace_seconds=600), consumer(10, "api", "prod"),
                rotate(100), ack(110, "api", 2), policy(200, 50),
                tick(300), tick(710), tick(800), end(900)]

    # h30 ends inside the granted window, so state.live differs too.
    s["h30"] = [config(grace_seconds=600), consumer(10, "api", "prod"),
                rotate(100), ack(110, "api", 2), policy(200, 50),
                tick(300), tick(400), end(500)]

    # h31 is the easy half: the policy lands before any grant, so every reading
    # that parses the record at all agrees.
    s["h31"] = [config(grace_seconds=1000), consumer(10, "api", "prod"),
                policy(50, 100), rotate(100), ack(110, "api", 2),
                tick(210), tick(300), end(400)]

    # -- stage membership is live, not snapshotted when the stage began -----
    # h32: a consumer registered mid-stage joins the cohort it must wait for.
    s["h32"] = [config(THREE), consumer(10, "d1", "dev"), rotate(100),
                consumer(120, "d2", "dev"), ack(130, "d1", 2), tick(200),
                ack(300, "d2", 2), tick(900), end(1000)]

    # h33: moving the only consumer out empties the staging environment, which
    # then completes on the move itself (6.1).
    s["h33"] = [config(THREE), consumer(10, "d1", "dev"), rotate(100),
                consumer(150, "d1", "prod"), tick(200), ack(250, "d1", 2),
                tick(900), end(1000)]

    # h34: a consumer leaves the staging environment mid-stage, so the stage
    # completes on the consumers that are left.
    s["h34"] = [config(THREE), consumer(10, "d1", "dev"), consumer(11, "p1", "prod"),
                consumer(12, "p2", "prod"), rotate(100), ack(110, "d1", 2),
                ack(120, "p1", 2), consumer(160, "p2", "staging"),
                tick(900), end(1000)]
    return s


# ------------------------------------------------------------------ archive
def archive():
    """The one capture that ships with the runner's own log beside it.

    Between them, the capture and the log pin down every behaviour that
    rotation-spec.md deliberately stops spelling out:

      * t=180 arrives after t=250, and the log stamps the resulting completion
        250 - the clock is a high-water mark;
      * rotate at 400 takes v3 after v2 rolled back - numbers are not reused;
      * the rollback names staging, dev, then prod - completed environments in
        reverse rollout order, then the one that was staging;
      * billing-api acks v3 at t=350, before v3 exists and long before prod
        stages, and prod still completes the instant it stages;
      * v1 is granted 600s at t=1000, the policy drops to 120s at t=1100, and
        the log revokes v1 at 1600, exactly on the boundary second;
      * stg-1 moves out of staging at 1720 and staging completes on the move,
        while checkout-7 registers into prod at 1740 and prod waits for it.
    """
    return [
        config(THREE, grace_seconds=600),
        consumer(10, "web-3", "dev"),
        consumer(14, "stg-1", "staging"),
        consumer(18, "billing-api", "prod"),
        health(20, "prod", False),
        rotate(100),
        tick(250),
        ack(180, "web-3", 2),          # merged in behind the tick
        ack(260, "stg-1", 2),
        health(300, "prod", True),
        ack(350, "billing-api", 3),    # before v3 exists, before prod stages
        rotate(400),
        ack(410, "web-3", 3),
        ack(1000, "stg-1", 3),
        policy(1100, 120),
        tick(1220),
        tick(1600),
        rotate(1700),
        ack(1710, "web-3", 4),
        consumer(1720, "stg-1", "dev"),        # staging is emptied mid-stage
        consumer(1740, "checkout-7", "prod"),  # joins prod while prod stages
        ack(1750, "billing-api", 4),
        tick(1780),
        ack(1790, "checkout-7", 4),
        tick(1910),
        end(2000),
    ]


class _Logged(reference_rotation.Rotator):
    """The reference, plus the annotation the live runner writes on revocation."""

    def __init__(self, cfg):
        super().__init__(cfg)
        self.notes = {}

    def _sweep_grace(self):
        pending = self.grace
        before = len(self.events)
        super()._sweep_grace()
        if pending is not None and len(self.events) > before:
            _version, started, window = pending
            self.notes[len(self.events) - 1] = "(granted %d, window %d)" % (
                started, window)


def _log_line(event, note):
    kind = event["kind"]
    if kind == "plan":
        body = "plan v%d [%s]" % (event["version"], ", ".join(event["envs"]))
    elif kind in ("stage", "complete", "rollback"):
        body = "%s %s v%d" % (kind, event["env"], event["version"])
    else:
        body = "%s v%d" % (kind, event["version"])
    return "%d %s%s" % (event["t"], body, (" " + note) if note else "")


def write_archive(records):
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
    (ARCHIVE / "rot-4417.session").write_text(text, encoding="utf-8", newline="\n")

    rotator = _Logged(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        getattr(rotator, reference_rotation.HANDLERS[record["op"]])(record)
        rotator._advance()
        rotator._sweep_grace()

    header = [
        "# rot-4417 - the runner's own log for the capture beside this file.",
        "# Written by the runner as it ran, one line per event it emitted:",
        "#",
        "#     <runner clock> <event>",
        "#",
        "# Not a reconstruction and not a summary. Where any other document in",
        "# this repository disagrees with this file, this file is what the",
        "# runner did.",
        "",
    ]
    body = [_log_line(e, rotator.notes.get(i))
            for i, e in enumerate(rotator.events)]
    (ARCHIVE / "rot-4417.runner.log").write_text(
        "\n".join(header + body) + "\n", encoding="utf-8", newline="\n")
    return rotator


def write(target, sessions):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(sessions.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".session")).write_text(text, encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())
    logged = write_archive(archive())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".session")).read_text(encoding="utf-8")
        expected[name] = reference_rotation.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")
    print("archive   : rot-4417.session + rot-4417.runner.log (%d log lines)"
          % len(logged.events))


if __name__ == "__main__":
    main()
