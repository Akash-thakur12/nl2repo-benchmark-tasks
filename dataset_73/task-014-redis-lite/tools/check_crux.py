#!/usr/bin/env python3
"""Prove the recovery/durability cruxes bite, by building the wrong-default
engine on purpose and checking the suite rejects it.

`check_mutations.py` perturbs operators; it can only see behaviour that is
already written down somewhere in the reference. This script is the complement:
each variant below is a *plausible implementation choice* - the thing a
competent engineer writes when they code from `instruction.md` alone and never
open `environment/docs/` or `environment/samples/`.

Every variant is produced by rewriting the reference engine, then the full
suite is run against it.

  caught     at least one test failed  -> the crux is load-bearing
  SURVIVOR   every test still passed   -> nothing in the suite depends on it

A SURVIVOR here is a defect in the task: it means a wrong reading scores the
same as the right one. The script exits non-zero if any variant survives.

This script does not ship in the task image, and contains no secrets beyond
what the reference engine already states.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
ENGINE = TASK / "solution" / "engine" / "engine.py"
TESTS = TASK / "tests" / "test_outputs.py"


def rewrite(source, pairs):
    """Apply (old, new) replacements, refusing to silently no-op."""
    for old, new in pairs:
        if old not in source:
            raise SystemExit(
                "check_crux.py is out of date with the reference engine; "
                "this snippet no longer appears:\n%s" % old)
        source = source.replace(old, new, 1)
    return source


# --------------------------------------------------------------- the snippets

TORN_BRANCH = """            if op is None:
                if unterminated_tail:
                    torn = True       # section 4.1: crash mid-append
                    break
                raise AOFCorruptError(       # section 4.2: real damage
                    "aof: bad record at line %d of %d; refusing to start"
                    % (number, total))
"""

TRUNCATE_GUARD = "        if torn:\n"

RPOP_REPLAY = """                lst.pop()
                if not lst:
                    # Invariant S2: a list key exists iff its list is non-empty.
                    # The live rpop drops the key here and so must recovery.
                    self._lists.pop(op[1], None)
"""

APPLY_LOOP = "        for op in records:\n"

SET_GUARD = """    def set(self, k, v):
        if k in self._lists:
            raise WrongTypeError(f"{k!r} holds a list")
        self._log(["set", k, v])
"""

LPUSH_GUARD = """    def lpush(self, k, v):
        if k in self._data:
            raise WrongTypeError(f"{k!r} holds a string")
        self._log(["lpush", k, v])
"""

DELETE_GUARD = """        existed = k in self._data or k in self._lists
        if existed:
            self._log(["del", k])
            self._data.pop(k, None)
"""


VARIANTS = [
    (
        "D / skip-the-bad-line: `except: continue`, file left alone",
        "The reflex loop. Unreadable records are skipped and the log is never "
        "truncated, so the next append is glued onto the surviving fragment.",
        [(TORN_BRANCH, "            if op is None:\n                continue\n"),
         (TRUNCATE_GUARD, "        if False:\n")],
    ),
    (
        "D / refuse-on-anything: every malformed record is fatal",
        "The other half of the coin: a crashed tail is treated as corruption, "
        "so the store cannot survive a power cut.",
        [(TORN_BRANCH,
          '            if op is None:\n'
          '                raise AOFCorruptError(\n'
          '                    "aof: bad record at line %d of %d" % (number, total))\n'),
         (TRUNCATE_GUARD, "        if False:\n")],
    ),
    (
        "D / discard the tail but do not truncate the file",
        "Halfway house: the recovered state is right, the file is still "
        "poisoned. Only the byte-level and second-restart tests can see it.",
        [(TRUNCATE_GUARD, "        if False:\n")],
    ),
    (
        "A / transcribe the record table: replayed rpop leaves the key at []",
        "Replay written as a literal reading of the AOF format table, without "
        "re-checking the invariants the live path maintains.",
        [(RPOP_REPLAY, "                lst.pop()\n")],
    ),
    (
        "C / follow aof_doctor.py: replay the record stream in reverse",
        "The shipped ops tool and the retired v1 note both say head-insertion "
        "means the log must be walked backwards. samples/basic says otherwise.",
        [(APPLY_LOOP, "        for op in reversed(records):\n")],
    ),
    (
        "H / log first, validate second",
        "The type check treated as a local guard rather than as what keeps the "
        "log truthful; plus a no-op DEL that still appends.",
        [(SET_GUARD,
          '    def set(self, k, v):\n'
          '        self._log(["set", k, v])\n'
          '        if k in self._lists:\n'
          '            raise WrongTypeError(f"{k!r} holds a list")\n'),
         (LPUSH_GUARD,
          '    def lpush(self, k, v):\n'
          '        self._log(["lpush", k, v])\n'
          '        if k in self._data:\n'
          '            raise WrongTypeError(f"{k!r} holds a string")\n'),
         (DELETE_GUARD,
          '        existed = k in self._data or k in self._lists\n'
          '        self._log(["del", k])\n'
          '        if existed:\n'
          '            self._data.pop(k, None)\n')],
    ),
]


def run_tests(engine_source, work):
    """(passed, failed) for the suite run against this engine source."""
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(ENGINE.parent, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "engine.py").write_text(engine_source, encoding="utf-8")

    environment = dict(os.environ)
    environment["ENGINE_DIR"] = str(package)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=300)
    tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    return result.returncode == 0, tail


def main():
    if not ENGINE.exists():
        print("no reference engine at %s" % ENGINE)
        return 1

    source = ENGINE.read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    try:
        clean, tail = run_tests(source, work)
        if not clean:
            print("BASELINE BROKEN: the reference engine does not pass its own "
                  "tests (%s). Nothing below would mean anything." % tail)
            return 1
        print("baseline: reference engine passes (%s)\n" % tail)

        survivors = []
        for label, rationale, pairs in VARIANTS:
            passed, tail = run_tests(rewrite(source, pairs), work)
            status = "SURVIVOR" if passed else "caught  "
            print("  %s  %s" % (status, label))
            print("            why an implementer writes it: %s" % rationale)
            print("            suite says: %s\n" % tail)
            if passed:
                survivors.append(label)

        if survivors:
            print("%d wrong-default implementation(s) passed the suite. Each "
                  "one is a reading the tests cannot distinguish from the "
                  "intended behaviour:" % len(survivors))
            for label in survivors:
                print("  SURVIVOR  %s" % label)
            return 1

        print("all %d wrong-default implementations are rejected by the suite."
              % len(VARIANTS))
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
