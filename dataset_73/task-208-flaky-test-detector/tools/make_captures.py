#!/usr/bin/env python3
"""Regenerate the sample and held-out capture corpora, and samples/expected.json.

  samples/          Six captures from a CI system having an ordinary week, where
                    nothing is flaky at all: every test either always passes or
                    always fails, one run per commit, one result per run, no
                    skips, no unknown statuses, nothing quarantined, and every
                    test in a capture seen in the same number of commits. Every
                    run comes back `completed`, every commit is spelled as a
                    full 40-character SHA exactly once, and the policy ledger
                    holds a single revision equal to the stamp. Almost every
                    plausible reading of the documentation reproduces
                    expected.json here.

  tests/captures/   Held-out captures covering the rest: retries inside a run,
                    several runs of one commit, failures spread across commits
                    rather than within one, skips, errors, unknown statuses,
                    both inclusive bounds, every tie-break, sticky quarantine,
                    a quarantined test that never ran, abbreviated and
                    upper-cased commit spellings, runs whose outcome publishes
                    no evidence, and policy and quarantine resolved as of the
                    capture.

This script does not ship in the task image.
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_flakiness  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "captures"

CAPTURED_AT = "2026-04-14T09:00:00Z"
BASE_EFFECTIVE = "2025-11-02T00:00:00Z"
HEX = "0123456789abcdefABCDEF"


def full(label):
    """A stable, realistic 40-character lowercase SHA for a logical commit."""
    digest = hashlib.sha1(("commit:" + label).encode("utf-8")).hexdigest()
    return digest


def short(label):
    """What linux-b writes: git rev-parse --short=7 HEAD."""
    return full(label)[:7]


def shout(label):
    """What the retired win-2019 pool wrote."""
    return short(label).upper()


def spell(label):
    """Pass an explicit commit spelling through; expand a logical label."""
    text = str(label)
    if len(text) in (7, 40) and all(c in HEX for c in text):
        return text
    return full(text)


def revision(effective_at, min_commits, threshold_percent):
    return {"effective_at": effective_at, "min_commits": min_commits,
            "threshold_percent": threshold_percent}


def roster(*entries):
    """Dated quarantine entries: (test, added_at[, lifted_at])."""
    out = []
    for entry in entries:
        row = {"test": entry[0], "added_at": entry[1]}
        if len(entry) > 2 and entry[2] is not None:
            row["lifted_at"] = entry[2]
        out.append(row)
    return out


def capture(runs, min_commits=5, threshold_percent=60, quarantined=None,
            captured_at=CAPTURED_AT, policy_history=None, stamp=None):
    """A capture. `stamp` overrides the cached top-level numbers; by default the
    stamp agrees with the single ledger revision."""
    if policy_history is None:
        policy_history = [revision(BASE_EFFECTIVE, min_commits, threshold_percent)]
    stamped = stamp if stamp is not None else (min_commits, threshold_percent)
    payload = {"captured_at": captured_at,
               "min_commits": stamped[0],
               "threshold_percent": stamped[1],
               "policy_history": policy_history,
               "runs": runs}
    if quarantined is not None:
        payload["quarantined"] = quarantined
    return payload


def run(run_id, commit, *results, **kwargs):
    return {"id": run_id, "commit": spell(commit),
            "outcome": kwargs.pop("outcome", "completed"),
            "results": [{"test": test, "status": status} for test, status in results]}


def steady(test, commit_prefix, count, status="passed", start=1):
    """One run per commit, the same status every time."""
    return [run("%s%d" % (commit_prefix, i), "%s%d" % (commit_prefix, i),
                (test, status))
            for i in range(start, start + count)]


# ------------------------------------------------------------ benign samples
def benign():
    # Nothing here is flaky at all: every test either always passes or always
    # fails, one run per commit, one result per run. That makes per-run and
    # per-commit accounting agree, leaves retries and skips out of the visible
    # corpus entirely, and pins every rate at zero so flooring never shows.
    # Every test in a capture appears in the same number of commits, so the
    # ranking never needs a tie broken on anything but the name. Neither bound
    # is ever met, so whether they are inclusive does not show either.
    def mixed(commits, *tests):
        return [run("r%d" % i, "c%d" % i, *[(name, status) for name, status in tests])
                for i in range(1, commits + 1)]

    s = {}
    s["s01"] = capture(mixed(3, ("t_login", "passed")))
    s["s02"] = capture(mixed(3, ("t_a", "passed"), ("t_b", "passed")))
    s["s03"] = capture(mixed(3, ("t_broken", "failed")))
    s["s04"] = capture(mixed(3, ("t_good", "passed"), ("t_bad", "failed")))
    s["s05"] = capture(mixed(4, ("t_x", "passed")))
    s["s06"] = capture(mixed(2, ("t_one", "passed"), ("t_two", "failed"),
                             ("t_three", "passed")))
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- a retry inside one run makes that commit flaky (1.5, 3.4) ---------
    s["h01"] = capture([run("r1", "c1", ("t", "passed"), ("t", "failed"))])

    # -- two runs of one commit are one commit (1.1, 3.1) ------------------
    s["h02"] = capture([run("r1", "c1", ("t", "failed")),
                        run("r2", "c1", ("t", "passed"))])

    s["h03"] = capture([run("r1", "c1", ("t", "passed")),
                        run("r2", "c1", ("t", "passed")),
                        run("r3", "c2", ("t", "failed")),
                        run("r4", "c2", ("t", "failed"))])

    # -- disagreement across commits is not flakiness (3.4) ----------------
    s["h04"] = capture([run("r1", "c1", ("t", "passed")),
                        run("r2", "c2", ("t", "failed")),
                        run("r3", "c3", ("t", "passed")),
                        run("r4", "c4", ("t", "failed"))])

    # -- error counts exactly as failure does (1.4) ------------------------
    s["h05"] = capture([run("r1", "c1", ("t", "passed"), ("t", "error"))])
    s["h06"] = capture([run("r1", "c1", ("t", "error")), run("r2", "c1", ("t", "failed"))])

    # -- a commit that was only ever skipped does not count (3.2) ----------
    s["h07"] = capture([run("r1", "c1", ("t", "skipped")),
                        run("r2", "c2", ("t", "passed")),
                        run("r3", "c3", ("t", "failed"))])

    s["h08"] = capture([run("r1", "c1", ("t", "skipped")),
                        run("r2", "c1", ("t", "skipped"))])

    # -- skips inside a counted commit are ignored (3.3) -------------------
    s["h09"] = capture([run("r1", "c1", ("t", "skipped"), ("t", "passed"),
                            ("t", "failed"))])
    s["h10"] = capture([run("r1", "c1", ("t", "skipped"), ("t", "passed"))])

    # -- an unknown status is recorded and discarded (1.3) -----------------
    s["h11"] = capture([run("r1", "c1", ("t", "aborted"), ("t", "passed"))])
    s["h12"] = capture([run("r1", "c1", ("t", "aborted"), ("t", "timeout")),
                        run("r2", "c2", ("t", "passed"), ("t", "failed"))])

    # -- rate is floored, not rounded (4.1) --------------------------------
    s["h13"] = capture([run("r1", "c1", ("t", "passed"), ("t", "failed")),
                        run("r2", "c2", ("t", "passed")),
                        run("r3", "c3", ("t", "passed"))])

    s["h14"] = capture([run("r1", "c1", ("t", "passed"), ("t", "failed")),
                        run("r2", "c2", ("t", "passed"), ("t", "failed")),
                        run("r3", "c3", ("t", "passed"))])

    s["h15"] = capture([run("r%d" % i, "c%d" % i, ("t", "passed")) for i in range(1, 7)]
                       + [run("rx", "cx", ("t", "passed"), ("t", "failed"))])

    # -- both bounds are inclusive (5.1) -----------------------------------
    s["h16"] = capture([run("r1", "c1", ("t", "passed"), ("t", "failed")),
                        run("r2", "c2", ("t", "passed"))],
                       min_commits=2, threshold_percent=50)

    s["h17"] = capture([run("r1", "c1", ("t", "passed"), ("t", "failed")),
                        run("r2", "c2", ("t", "passed"))],
                       min_commits=3, threshold_percent=50)

    s["h18"] = capture([run("r1", "c1", ("t", "passed"), ("t", "failed")),
                        run("r2", "c2", ("t", "passed"))],
                       min_commits=2, threshold_percent=51)

    # -- ties break on commits, then on name (4.2) -------------------------
    s["h19"] = capture(
        [run("r1", "c1", ("t_b", "passed"), ("t_b", "failed"),
             ("t_a", "passed"), ("t_a", "failed")),
         run("r2", "c2", ("t_a", "passed"), ("t_a", "failed"))])

    s["h20"] = capture(
        [run("r1", "c1", ("zebra", "passed"), ("zebra", "failed"),
             ("alpha", "passed"), ("alpha", "failed"),
             ("middle", "passed"), ("middle", "failed"))])

    s["h21"] = capture(
        [run("r1", "c1", ("low", "passed"), ("high", "passed"), ("high", "failed")),
         run("r2", "c2", ("low", "passed"), ("low", "failed")),
         run("r3", "c3", ("low", "passed"))])

    # -- quarantine is sticky (5.2) ----------------------------------------
    s["h22"] = capture(steady("t_legacy", "c", 4), quarantined=roster(("t_legacy", "2026-01-06T00:00:00Z")))

    s["h23"] = capture(steady("t_legacy", "c", 4), quarantined=roster(("t_legacy", "2026-01-06T00:00:00Z")),
                       min_commits=1, threshold_percent=0)

    # -- quarantine does not invent history (5.3) --------------------------
    s["h24"] = capture(steady("t_real", "c", 2), quarantined=roster(("t_never_ran", "2026-01-06T00:00:00Z")))

    # -- a test that only ever skipped is absent (4.3) ---------------------
    s["h25"] = capture([run("r1", "c1", ("t_seen", "passed"), ("t_ghost", "skipped")),
                        run("r2", "c2", ("t_seen", "failed"), ("t_ghost", "skipped"))])

    # -- a renamed test keeps nothing (2.2) --------------------------------
    s["h26"] = capture([run("r1", "c1", ("suite.old", "passed"), ("suite.old", "failed")),
                        run("r2", "c2", ("suite.new", "passed"))])

    # -- several tests, mixed outcomes, low bounds -------------------------
    s["h27"] = capture(
        [run("r1", "c1", ("t_a", "passed"), ("t_a", "failed"),
             ("t_b", "passed"), ("t_c", "skipped")),
         run("r2", "c1", ("t_b", "error")),
         run("r3", "c2", ("t_a", "passed"), ("t_b", "passed"), ("t_c", "passed")),
         run("r4", "c3", ("t_a", "failed"), ("t_b", "passed"), ("t_c", "nope"))],
        min_commits=2, threshold_percent=30, quarantined=roster(("t_c", "2026-01-06T00:00:00Z")))

    # -- no runs at all -----------------------------------------------------
    s["h28"] = capture([])
    s["h29"] = capture([], quarantined=roster(("t_gone", "2026-01-06T00:00:00Z")))

    # -- a threshold of zero recommends everything that meets min_commits ---
    s["h30"] = capture(steady("t_stable", "c", 3), min_commits=3, threshold_percent=0)
    # -- equal rates, and the test with more commits sorts later by name ---
    s["h31"] = capture(
        [run("r1", "c1", ("t_zz", "passed"), ("t_zz", "failed"),
             ("t_aa", "passed"), ("t_aa", "failed")),
         run("r2", "c2", ("t_zz", "passed"), ("t_zz", "failed"))])

    # -- the recommendation list follows the ranking, not the alphabet -----
    s["h32"] = capture(
        [run("r1", "c1", ("zebra", "passed"), ("zebra", "failed"),
             ("alpha", "passed"))],
        min_commits=1, threshold_percent=0)

    # ================================================================
    # Commit identity: the same revision, spelled by different pools.
    # ================================================================

    # -- full, abbreviated and upper-cased spellings of ONE commit ---------
    s["h33"] = capture(
        [run("r1", full("k1"), ("t", "failed")),
         run("r2", short("k1"), ("t", "passed")),
         run("r3", shout("k1"), ("t", "passed"))],
        min_commits=1, threshold_percent=50)

    # -- case alone separates two runs of one commit -----------------------
    s["h34"] = capture(
        [run("r1", shout("k2"), ("t", "passed")),
         run("r2", short("k2"), ("t", "failed"))],
        min_commits=1, threshold_percent=50)

    # -- two genuinely distinct revisions, each spelled two ways -----------
    s["h35"] = capture(
        [run("r1", full("k3"), ("t", "passed")),
         run("r2", short("k3"), ("t", "failed")),
         run("r3", full("k4"), ("t", "passed")),
         run("r4", short("k4"), ("t", "passed"))],
        min_commits=2, threshold_percent=50)

    # -- canonicalisation changes the ranking order ------------------------
    s["h36"] = capture(
        [run("r1", full("k5"), ("t_a", "failed")),
         run("r2", short("k5"), ("t_a", "passed")),
         run("r3", full("k6"), ("t_b", "passed"), ("t_b", "failed")),
         run("r4", full("k7"), ("t_b", "passed")),
         run("r5", full("k8"), ("t_b", "passed"))],
        min_commits=1, threshold_percent=90)

    # ================================================================
    # Run outcomes: only some runs publish evidence.
    # ================================================================

    # -- an infra_error run wrote a placeholder failure; the retry passed --
    s["h37"] = capture(
        [run("r1", full("k9"), ("t", "failed"), outcome="infra_error"),
         run("r2", short("k9"), ("t", "passed"))],
        min_commits=1, threshold_percent=50)

    # -- a placeholder unknown status inside a lost run is not an error ----
    s["h38"] = capture(
        [run("r1", full("k10"), ("t", "aborted"), ("t", "failed"),
             outcome="agent_lost"),
         run("r2", full("k10"), ("t", "passed"))],
        min_commits=1, threshold_percent=50)

    # -- a test seen only inside a cancelled run is absent entirely --------
    s["h39"] = capture(
        [run("r1", full("k11"), ("t_seen", "passed")),
         run("r2", full("k11"), ("t_ghost", "failed"), ("t_ghost", "passed"),
             outcome="cancelled")],
        min_commits=1, threshold_percent=0)

    # -- a commit whose only run for a test is discarded does not count ----
    s["h40"] = capture(
        [run("r1", full("k12"), ("t", "failed"), outcome="infra_error"),
         run("r2", full("k13"), ("t", "passed")),
         run("r3", full("k14"), ("t", "passed"))],
        min_commits=1, threshold_percent=0)

    # -- timed_out and failed builds really ran, so they are evidence ------
    s["h41"] = capture(
        [run("r1", full("k15"), ("t", "passed"), outcome="timed_out"),
         run("r2", full("k15"), ("t", "failed"), outcome="failed")],
        min_commits=1, threshold_percent=100)

    # ================================================================
    # Policy and quarantine as of the capture.
    # ================================================================

    # -- the stamp lags a revision that had already taken effect -----------
    s["h42"] = capture(
        [run("r1", "c1", ("t", "passed"), ("t", "failed")),
         run("r2", "c2", ("t", "passed")),
         run("r3", "c3", ("t", "passed")),
         run("r4", "c4", ("t", "passed"))],
        stamp=(5, 60),
        policy_history=[revision(BASE_EFFECTIVE, 5, 60),
                        revision("2026-04-01T00:00:00Z", 2, 25)])

    # -- an auditor back-filled a revision that is not in force yet --------
    s["h43"] = capture(
        [run("r1", "c1", ("t", "passed"), ("t", "failed")),
         run("r2", "c2", ("t", "passed")),
         run("r3", "c3", ("t", "passed")),
         run("r4", "c4", ("t", "passed"))],
        stamp=(2, 25),
        policy_history=[revision(BASE_EFFECTIVE, 5, 60),
                        revision("2026-04-01T00:00:00Z", 2, 25),
                        revision("2026-06-01T00:00:00Z", 3, 40)])

    # -- the ledger is not sorted, so "the last entry" is not the answer ---
    s["h44"] = capture(
        [run("r1", "c1", ("t", "passed"), ("t", "failed")),
         run("r2", "c2", ("t", "passed")),
         run("r3", "c3", ("t", "passed")),
         run("r4", "c4", ("t", "passed"))],
        stamp=(2, 25),
        policy_history=[revision("2026-04-01T00:00:00Z", 2, 25),
                        revision("2026-06-01T00:00:00Z", 3, 40),
                        revision(BASE_EFFECTIVE, 5, 60)])

    # -- a quarantine lifted before the capture is not in force ------------
    s["h45"] = capture(
        steady("t_old", "c", 3),
        quarantined=roster(("t_old", "2026-01-06T00:00:00Z",
                            "2026-03-01T00:00:00Z")))

    # -- a quarantine added after the capture is not in force yet ----------
    s["h46"] = capture(
        steady("t_future", "c", 3),
        quarantined=roster(("t_future", "2026-05-01T00:00:00Z")))

    # -- an entry still in force is sticky; a lifted sibling is not --------
    s["h47"] = capture(
        steady("t_legacy", "a", 3) + steady("t_gone", "b", 3),
        quarantined=roster(("t_legacy", "2026-01-06T00:00:00Z"),
                           ("t_gone", "2026-01-06T00:00:00Z",
                            "2026-02-02T00:00:00Z")))

    # ================================================================
    # All three mechanisms at once.
    # ================================================================
    s["h48"] = capture(
        [run("r1", full("m1"), ("t_flap", "passed"), ("t_sticky", "passed"),
             ("t_lifted", "passed")),
         run("r2", full("m1"), ("t_flap", "failed"), ("t_ghost", "failed"),
             outcome="infra_error"),
         run("r3", short("m1"), ("t_flap", "passed"), ("t_sticky", "passed"),
             ("t_lifted", "passed")),
         run("r4", full("m2"), ("t_flap", "passed"), ("t_sticky", "passed"),
             ("t_lifted", "passed")),
         run("r5", shout("m2"), ("t_flap", "failed")),
         run("r6", full("m3"), ("t_flap", "vanished"), outcome="agent_lost"),
         run("r7", full("m3"), ("t_flap", "passed"), ("t_sticky", "failed"),
             ("t_lifted", "failed"))],
        stamp=(5, 60),
        policy_history=[revision(BASE_EFFECTIVE, 5, 60),
                        revision("2026-08-01T00:00:00Z", 4, 90),
                        revision("2026-03-20T00:00:00Z", 2, 30)],
        quarantined=roster(("t_sticky", "2026-01-06T00:00:00Z"),
                           ("t_lifted", "2025-12-01T00:00:00Z",
                            "2026-02-02T00:00:00Z")))

    return s


def write(target, captures):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(captures.items()):
        (target / (name + ".capture")).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".capture")).read_text(encoding="utf-8")
        expected[name] = reference_flakiness.rank_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
