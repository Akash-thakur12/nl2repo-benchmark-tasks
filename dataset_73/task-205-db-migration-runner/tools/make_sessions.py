#!/usr/bin/env python3
"""Regenerate the sample and held-out session corpora, samples/expected.json
and samples/checksums.json.

  samples/          Seven sessions from a repository that has been looked after:
                    single-digit versions applied in order, every migration
                    reversible and transactional, no drift, no deleted files,
                    no failures, no repeatable migrations and no lock
                    contention. Almost every plausible reading of the
                    specification reproduces expected.json here, including the
                    one `baseline` record, which sits where every reading of it
                    agrees.

  samples/          checksums.json is the normative digest table spec 1.3 names.
                    Fourteen rows, each isolating one transform, chosen so that
                    exactly one normalisation rule satisfies all of them.

  tests/sessions/   Held-out sessions covering the rest: two-digit versions where
                    text order and numeric order disagree, checksum drift, files
                    that were reformatted but not changed, deleted files,
                    out-of-order arrivals, a baseline that moves mid-session,
                    targets in both directions, irreversible rollbacks, failures
                    with and without a transaction, the dirty latch, what repair
                    does and does not put right, lock contention, and repeatable
                    migrations including one that fails.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_runner  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"


def config(allow_out_of_order=False, baseline=0):
    return {"op": "config", "allow_out_of_order": allow_out_of_order,
            "baseline": baseline}


def define(version, name, up=None, down=None, transactional=True, fails=False):
    record = {"op": "define", "version": version, "name": name,
              "up": up if up is not None else "UP " + str(version),
              "transactional": transactional, "fails": fails}
    if down is not None:
        record["down"] = down
    return record


def repeatable(name, up, fails=False, transactional=True):
    return {"op": "define", "name": name, "up": up,
            "transactional": transactional, "fails": fails}


def undefine(version):
    return {"op": "undefine", "version": version}


def history(version, checksum):
    return {"op": "history", "version": version, "checksum": checksum}


def lock(held):
    return {"op": "lock", "held": held}


def baseline(version):
    return {"op": "baseline", "version": version}


def cmd(name, **kw):
    record = {"op": "command", "cmd": name}
    record.update(kw)
    return record


def end():
    return {"op": "end"}


def digest(up, down=None):
    return reference_runner.checksum_of(up, down)


def reversible(version):
    return define(version, "m%d" % version, up="UP %d" % version,
                  down="DOWN %d" % version)


# ------------------------------------------------------------ benign samples
def benign():
    s = {}

    # Every command here names its step count explicitly, so a runner that
    # defaults `up` to a single step still reproduces the samples. The held-out
    # corpus is where the default has to be right.
    s["s01"] = [config(), reversible(1), reversible(2), cmd("up", steps=2), end()]

    s["s02"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("up", steps=2), end()]

    s["s03"] = [config(), reversible(1), reversible(2),
                history(1, digest("UP 1", "DOWN 1")),
                cmd("up", steps=1), end()]

    s["s04"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("up", steps=3), cmd("up", steps=3), end()]

    s["s05"] = [config(), reversible(1), cmd("up"), cmd("down", steps=1), end()]

    s["s06"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("up", steps=1), cmd("up", steps=1), cmd("up", steps=1), end()]

    # A `baseline` record in a position where every reading of it agrees:
    # nothing is applied yet and the only definition is above the new floor, so
    # the move changes no answer. It is here so that a tool meets the record at
    # least once before it meets one that matters.
    s["s07"] = [config(), reversible(2), baseline(1), cmd("up"), end()]
    return s


# ------------------------------------------------ the normative digest table
def checksum_rows():
    """Rows the production runner emitted, for spec 1.3.

    Each row isolates one transform. Together they admit exactly one rule:
    normalise each body (CRLF and lone CR to LF, trailing spaces and tabs off
    every line, trailing blank lines dropped, nothing else touched) and then
    concatenate the two normalised bodies with no separator.

    The last two rows are the ones that fix the *order* of normalise and
    concatenate: both hash as "AB", which concatenating first would render as
    "A  B" and "A\\nB".
    """
    pairs = [
        ("A", None),                # plain sha256, lower hex, utf-8
        ("A", "B"),                 # concatenation, no separator
        ("A\nB", None),             # the anchor the next five must match
        ("A\r\nB", None),           # CRLF
        ("A\rB", None),             # lone CR
        ("A  \nB", None),           # trailing spaces
        ("A\t\nB\t", None),         # trailing tabs
        ("A\nB\n\n\n", None),       # trailing blank lines
        ("A\n\nB", None),           # negative: an interior blank line counts
        (" A\nB", None),            # negative: leading indent counts
        ("a\nb", None),             # negative: case counts
        ("A\nB", "C\r\nD  "),       # down is normalised too
        ("A  ", "B"),               # order: normalise, then concatenate
        ("A\n", "B"),               # order: normalise, then concatenate
    ]
    return [{"up": up, "down": down, "sha256": digest(up, down)}
            for up, down in pairs]


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- numeric ordering, not text ordering (1.4) -------------------------
    s["h01"] = [config(), reversible(9), reversible(10), reversible(11),
                cmd("up"), end()]

    s["h02"] = [config(), reversible(2), reversible(10),
                cmd("up", steps=1), end()]

    s["h03"] = [config(), reversible(9), reversible(10),
                cmd("up"), cmd("down", steps=1), end()]

    # -- checksum drift halts everything (3.3) -----------------------------
    s["h04"] = [config(), reversible(1), reversible(2),
                history(1, digest("OLD", "OLD")),
                cmd("up"), end()]

    s["h05"] = [config(), reversible(1), reversible(2),
                history(1, digest("OLD", "OLD")),
                history(2, digest("ALSO OLD", "OLD")),
                cmd("up"), end()]

    # -- a deleted file for an applied migration (3.4) ---------------------
    s["h06"] = [config(), reversible(1), reversible(2),
                history(1, digest("UP 1", "DOWN 1")),
                undefine(1),
                cmd("up"), end()]

    # -- drift is reported before missing (3.3 before 3.4) -----------------
    s["h07"] = [config(), reversible(1), reversible(2), reversible(3),
                history(2, digest("OLD", "OLD")),
                history(3, digest("UP 3", "DOWN 3")),
                undefine(3),
                cmd("up"), end()]

    # -- an unapplied migration behind current (3.5) -----------------------
    s["h08"] = [config(), reversible(1), reversible(3),
                history(3, digest("UP 3", "DOWN 3")),
                cmd("up"), end()]

    s["h09"] = [config(allow_out_of_order=True), reversible(1), reversible(3),
                history(3, digest("UP 3", "DOWN 3")),
                cmd("up"), end()]

    # -- baseline hides everything at or below it (2, 3.4, 4.2) ------------
    s["h10"] = [config(baseline=5), reversible(6), reversible(7),
                cmd("up"), cmd("down", steps=5), end()]

    s["h11"] = [config(baseline=5), reversible(6),
                history(3, digest("GONE", "GONE")),
                cmd("up"), end()]

    # -- irreversible rollback (5.2) ---------------------------------------
    s["h12"] = [config(), define(1, "m1", up="UP 1"),
                cmd("up"), cmd("down"), end()]

    s["h13"] = [config(), reversible(1), define(2, "m2", up="UP 2"),
                cmd("up"), cmd("down", steps=2), end()]

    # -- failures, transactional and not (5.3, 5.4, 5.5) -------------------
    s["h14"] = [config(), reversible(1), define(2, "m2", up="UP 2", down="DOWN 2",
                                                fails=True),
                reversible(3),
                cmd("up"), end()]

    s["h15"] = [config(), reversible(1),
                define(2, "m2", up="UP 2", down="DOWN 2", fails=True,
                       transactional=False),
                cmd("up"), end()]

    # -- the dirty latch blocks later commands until repair (3.2, 4.5) -----
    s["h16"] = [config(), reversible(1),
                define(2, "m2", up="UP 2", down="DOWN 2", fails=True,
                       transactional=False),
                cmd("up"), cmd("up"), cmd("repair"), cmd("up"), end()]

    # -- repair rewrites the recorded checksums (4.5) ----------------------
    s["h17"] = [config(), reversible(1), reversible(2),
                history(1, digest("OLD", "OLD")),
                cmd("up"), cmd("repair"), cmd("up"), end()]

    # -- the lock is checked before everything else (3.1) ------------------
    s["h18"] = [config(), reversible(1),
                history(1, digest("OLD", "OLD")),
                lock(True), cmd("up"), lock(False), cmd("up"), end()]

    s["h19"] = [config(), reversible(1),
                define(2, "m2", up="UP 2", down="DOWN 2", fails=True,
                       transactional=False),
                cmd("up"), lock(True), cmd("repair"), lock(False),
                cmd("repair"), cmd("up"), end()]

    # -- to, forwards and backwards (4.3, 4.4) -----------------------------
    s["h20"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("to", target=2), end()]

    s["h21"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("up"), cmd("to", target=1), end()]

    s["h22"] = [config(), reversible(1), reversible(2),
                cmd("up"), cmd("to", target=0), end()]

    s["h23"] = [config(), reversible(1), reversible(2),
                cmd("to", target=9), end()]

    s["h24"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("up"), cmd("to", target=3), end()]

    # -- to backwards stops at the baseline (4.3) --------------------------
    s["h25"] = [config(baseline=5), reversible(6), reversible(7),
                cmd("up"), cmd("to", target=0), end()]

    # -- repeatable migrations run after a clean versioned phase (6.1) -----
    s["h26"] = [config(), reversible(1),
                repeatable("R__b_views", "SELECT 2"),
                repeatable("R__a_grants", "SELECT 1"),
                cmd("up"), end()]

    # -- and only when their checksum changed (6.1, 6.2) -------------------
    s["h27"] = [config(), reversible(1), reversible(2),
                repeatable("R__views", "SELECT 1"),
                cmd("up", steps=1), cmd("up", steps=1), end()]

    s["h28"] = [config(), reversible(1), reversible(2),
                repeatable("R__views", "SELECT 1"),
                cmd("up", steps=1),
                repeatable("R__views", "SELECT 2"),
                cmd("up", steps=1), end()]

    # -- never on down, never after an error (6.3) -------------------------
    s["h29"] = [config(), reversible(1),
                repeatable("R__views", "SELECT 1"),
                cmd("up"), cmd("down"), end()]

    s["h30"] = [config(), reversible(1),
                define(2, "m2", up="UP 2", down="DOWN 2", fails=True),
                repeatable("R__views", "SELECT 1"),
                cmd("up"), end()]

    # -- a repeatable migration is not part of current (6.3) ---------------
    s["h31"] = [config(), repeatable("R__views", "SELECT 1"),
                cmd("up"), end()]

    # -- redefining a version replaces it (1.5) ----------------------------
    s["h32"] = [config(), reversible(1),
                define(1, "m1_rewritten", up="UP 1 NEW", down="DOWN 1 NEW"),
                cmd("up"), end()]

    # -- down with more steps than are applied (4.2) -----------------------
    s["h33"] = [config(), reversible(1), reversible(2),
                cmd("up"), cmd("down", steps=9), end()]

    # -- up with more steps than are pending (4.1) -------------------------
    s["h34"] = [config(), reversible(1), cmd("up", steps=9), end()]
    # -- down stops at the baseline even when history reaches below it (4.2)
    s["h35"] = [config(baseline=5), reversible(6),
                history(3, digest("ANCIENT", "ANCIENT")),
                cmd("up"), cmd("down", steps=5), end()]

    # -- the lock outranks the dirty latch (3.1 before 3.2) ----------------
    s["h36"] = [config(), reversible(1),
                define(2, "m2", up="UP 2", down="DOWN 2", fails=True,
                       transactional=False),
                cmd("up"), lock(True), cmd("up"), end()]

    # -- down with no steps rolls back exactly one (4.2) -------------------
    s["h37"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("up"), cmd("down"), end()]

    # -- a changed repeatable still does not run on down (6.3) -------------
    s["h38"] = [config(), reversible(1), reversible(2),
                repeatable("R__views", "SELECT 1"),
                cmd("up"),
                repeatable("R__views", "SELECT 2"),
                cmd("down"), end()]

    # ------------------------------------------------------------------
    # 1.3 and samples/checksums.json: the digest is taken over the bodies as
    # the runner stores them. A file that was reformatted but not changed is
    # not drift; a file that really changed still is.
    # ------------------------------------------------------------------

    # -- a Windows checkout: CRLF everywhere, same content -----------------
    s["h39"] = [config(),
                define(1, "m1", up="UP 1\r\n", down="DOWN 1\r\n"),
                reversible(2),
                history(1, digest("UP 1", "DOWN 1")),
                cmd("up"), end()]

    # -- an editor that trims on save, plus stray blank lines at the end ----
    s["h40"] = [config(),
                define(1, "m1", up="UP 1   \n\n\n", down="DOWN 1\t"),
                reversible(2),
                history(1, digest("UP 1", "DOWN 1")),
                cmd("up"), end()]

    # -- a lone CR (an old Mac checkout), and a reformatted `down` ----------
    s["h41"] = [config(),
                define(1, "m1", up="ALTER A\rALTER B", down="DROP B\r\nDROP A  "),
                reversible(2),
                history(1, digest("ALTER A\nALTER B", "DROP B\nDROP A")),
                cmd("up"), end()]

    # -- a real edit is still drift: re-indenting changes the body ---------
    s["h42"] = [config(),
                define(1, "m1", up="  UP 1", down="DOWN 1"),
                reversible(2),
                history(1, digest("UP 1", "DOWN 1")),
                cmd("up"), end()]

    # -- normalise then concatenate, not the other way round: trailing
    #    spaces at the end of `up` must not survive into the digest --------
    s["h43"] = [config(),
                define(1, "m1", up="UP 1  ", down="DOWN 1"),
                reversible(2),
                history(1, digest("UP 1", "DOWN 1")),
                cmd("up"), end()]

    # -- the same, with a trailing newline instead of trailing spaces ------
    s["h44"] = [config(),
                define(1, "m1", up="UP 1\n", down="DOWN 1"),
                reversible(2),
                history(1, digest("UP 1", "DOWN 1")),
                cmd("up"), end()]

    # -- 1.3 into 6.1: a repeatable that was reformatted has not changed ---
    s["h45"] = [config(), reversible(1), reversible(2),
                repeatable("R__views", "SELECT 1"),
                cmd("up", steps=1),
                repeatable("R__views", "SELECT 1  \r\n"),
                cmd("up", steps=1), end()]

    # -- DRIFT names the lowest *actually* drifted version, not the lowest
    #    file that happens to look different byte for byte ----------------
    s["h46"] = [config(),
                define(1, "m1", up="UP 1\r\n", down="DOWN 1"),
                define(2, "m2", up="UP 2 CHANGED", down="DOWN 2"),
                reversible(3),
                history(1, digest("UP 1", "DOWN 1")),
                history(2, digest("UP 2", "DOWN 2")),
                cmd("up"), end()]

    # ------------------------------------------------------------------
    # The `baseline` record: the floor moves, and every check uses the floor
    # in force when the command runs.
    # ------------------------------------------------------------------

    # -- raised above current: down rolls nothing back, history is kept,
    #    current is the baseline rather than null -------------------------
    s["h47"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("up", steps=2),
                baseline(5),
                cmd("down", steps=2), end()]

    # -- a command refused DRIFT succeeds once the move exempts the row ----
    s["h48"] = [config(), reversible(1), reversible(2),
                history(1, digest("OLD", "OLD")),
                cmd("up"),
                baseline(1),
                cmd("up"), end()]

    # -- down and `to 0` both stop at the floor in force at that moment ----
    s["h49"] = [config(), reversible(1), reversible(2), reversible(3),
                reversible(4),
                cmd("up", steps=3),
                baseline(3),
                cmd("down", steps=5), cmd("up"), cmd("to", target=0), end()]

    # -- lowering a badly set baseline re-exposes the same rows ------------
    s["h50"] = [config(), reversible(1), reversible(2), reversible(3),
                cmd("up", steps=3),
                baseline(3),
                cmd("down", steps=1),
                baseline(1),
                cmd("down", steps=1), cmd("down", steps=1), end()]

    # -- the move exempts MISSING too, and shrinks the pending set ---------
    s["h51"] = [config(), reversible(2), reversible(3),
                history(1, digest("GONE", "GONE")),
                cmd("up"),
                baseline(1),
                cmd("up"), end()]

    # -- and it shrinks the out-of-order window --------------------------
    s["h52"] = [config(), reversible(1), reversible(3), reversible(4),
                history(3, digest("UP 3", "DOWN 3")),
                cmd("up"),
                baseline(1),
                cmd("up"), end()]

    # ------------------------------------------------------------------
    # What repair does and does not put right (4.5, docs/runbook.md).
    # ------------------------------------------------------------------

    # -- repair cannot invent a digest for a file that is gone, and must not
    #    drop the row to make the complaint go away ------------------------
    s["h53"] = [config(), reversible(1), reversible(2),
                history(1, digest("UP 1", "DOWN 1")),
                undefine(1),
                cmd("up"), cmd("repair"), cmd("up"),
                reversible(1),
                cmd("up"), end()]

    # -- repair does not bless a repeatable that changed during the incident
    s["h54"] = [config(), reversible(1),
                repeatable("R__views", "SELECT 1"),
                cmd("up"),
                repeatable("R__views", "SELECT 2"),
                define(2, "m2", up="UP 2", down="DOWN 2", fails=True,
                       transactional=False),
                cmd("up"), cmd("repair"),
                reversible(2),
                cmd("up"), end()]

    # -- repair reconciles rows under the floor too, which only shows once
    #    the floor comes back down ----------------------------------------
    s["h55"] = [config(baseline=2), reversible(1), reversible(2), reversible(3),
                reversible(4),
                history(1, digest("HAND EDIT", "HAND EDIT")),
                history(2, digest("UP 2", "DOWN 2")),
                cmd("up", steps=1), cmd("repair"),
                baseline(0),
                cmd("up"), end()]

    # ------------------------------------------------------------------
    # A repeatable migration that fails has no version to name (6.4).
    # ------------------------------------------------------------------

    # -- non-transactional: version null, dirty latched, the next repeatable
    #    in name order does not run, the versioned work stays applied ------
    s["h56"] = [config(), reversible(1), reversible(2),
                repeatable("R__a_totals", "SELECT BAD", fails=True,
                           transactional=False),
                repeatable("R__b_grants", "SELECT 1"),
                cmd("up"), cmd("up"), end()]

    # -- transactional: version null, runner stays clean, and the digest was
    #    never recorded so it is retried on the next command ---------------
    s["h57"] = [config(), reversible(1), reversible(2),
                repeatable("R__x", "SELECT BAD", fails=True),
                cmd("up", steps=1),
                repeatable("R__x", "SELECT BAD"),
                cmd("up", steps=1), end()]

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
        expected[name] = reference_runner.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    (SAMPLES / "checksums.json").write_text(
        json.dumps(checksum_rows(), indent=2) + "\n",
        encoding="utf-8", newline="\n")

    print("samples   : %d" % len(samples))
    print("held-out  : %d" % len(held_out()))
    print("checksums : %d rows" % len(checksum_rows()))
    print("expected.json written")


if __name__ == "__main__":
    main()
