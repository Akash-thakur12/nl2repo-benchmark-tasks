#!/usr/bin/env python3
"""Prove that the cruxes bite.

For each crux this task is built around there is an "obvious" implementation - a
plausible reading of the spec that a careful-but-hurried engineer would write.
This script produces each of those wrong-default engines by patching the
reference implementation, runs the full test suite against it, and asserts that
the suite notices.

  BITES     at least one test failed  -> the crux is worth points
  SURVIVOR  every test still passed   -> the suite does not depend on the crux

A SURVIVOR is a defect in the task, not in the implementation: it means the
wrong default is indistinguishable from the right answer under the tests.

The patches are textual edits against solution/engine/*.py.  They ship no secret
beyond what environment/docs and environment/samples already state.

    python tools/check_crux.py

This script does not ship in the task image.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
SRC = TASK / "solution" / "engine"
TESTS = TASK / "tests" / "test_outputs.py"


# --------------------------------------------------------------------------
# Each entry: (letter, name, file, [(old, new), ...])
# --------------------------------------------------------------------------

WRONG_DEFAULTS = [
    (
        "E",
        "recency read from the filename sequence number instead of the manifest",
        "engine.py",
        [(
            """        entries = None
        try:
            with open(self._manifest_path(), "r", encoding="utf-8") as fp:
                entries = json.load(fp).get("segments", [])
        except (OSError, ValueError):
            entries = None

        if entries is None:
            names = sorted(""",
            """        entries = None
        if entries is None:
            names = sorted(""",
        )],
    ),
    (
        "E",
        "next segment number = highest seen + 1 (cannot wrap, overflows the field)",
        "engine.py",
        [(
            """        if not self._segments:
            seq = 0
        else:
            seq = (self._segments[-1]["seq"] + 1) % SEQ_MODULUS
        while seq in live:
            seq = (seq + 1) % SEQ_MODULUS
        return seq""",
            """        return (max(live) + 1) if live else 0""",
        )],
    ),
    (
        "H",
        "every compaction drops tombstoned keys",
        "engine.py",
        [(
            "merged = self._merge(inputs, drop_tombstones=not below)",
            "merged = self._merge(inputs, drop_tombstones=True)",
        )],
    ),
    (
        "H",
        "compaction always merges the whole store into one segment",
        "engine.py",
        [(
            """        if self._count_level(0) > self._level0_max:
            self._minor_compact()
        if self._count_level(1) > self._level0_max:
            self._major_compact()""",
            """        if len(self._segments) > self._level0_max:
            self.compact()""",
        )],
    ),
    (
        "D",
        "WAL replay applies every record in file order (the v1 rule)",
        "engine.py",
        [(
            """            if seq != expected:
                break""",
            """            expected = seq""",
        )],
    ),
    (
        "D",
        "WAL replay skips odd-looking records and keeps going",
        "engine.py",
        [(
            """            if seq != expected:
                break""",
            """            if seq != expected:
                expected = seq""",
        )],
    ),
    (
        "D",
        "WAL replay keeps the highest seq seen per key",
        "engine.py",
        [(
            """            if seq != expected:
                break
            if op == "p":
                self._mem[key] = val
            elif op == "d":
                self._mem[key] = _TOMBSTONE
            else:
                break""",
            """            if seq < getattr(self, "_seen", {}).get(key, 0):
                continue
            if not hasattr(self, "_seen"):
                self._seen = {}
            self._seen[key] = seq
            if op == "p":
                self._mem[key] = val
            elif op == "d":
                self._mem[key] = _TOMBSTONE""",
        )],
    ),
    (
        "trace",
        "flush trigger counts distinct MemTable keys, not buffered writes",
        "engine.py",
        [(
            "if self._pending >= self._memtable_limit:",
            "if len(self._mem) >= self._memtable_limit:",
        )],
    ),
]


def run_suite(engine_dir):
    env = dict(os.environ, ENGINE_DIR=str(engine_dir))
    res = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no", "-p", "no:cacheprovider"],
        capture_output=True, text=True, env=env, cwd=str(TASK),
    )
    return res.returncode, res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""


def main():
    print("baseline: the reference implementation must pass")
    rc, line = run_suite(SRC)
    print(f"  {line}")
    if rc != 0:
        print("BASELINE FAILED - fix solution/ before reading anything below")
        return 1

    survivors = []
    for letter, name, filename, edits in WRONG_DEFAULTS:
        tmp = tempfile.mkdtemp(prefix="crux_")
        dst = pathlib.Path(tmp) / "engine"
        shutil.copytree(SRC, dst)
        target = dst / filename
        text = target.read_text(encoding="utf-8")
        for old, new in edits:
            if old not in text:
                print(f"[{letter}] {name}\n  PATCH DID NOT APPLY - update this script")
                survivors.append((letter, name))
                text = None
                break
            text = text.replace(old, new, 1)
        if text is None:
            continue
        target.write_text(text, encoding="utf-8")
        rc, line = run_suite(dst)
        verdict = "BITES   " if rc != 0 else "SURVIVOR"
        print(f"[{letter}] {verdict} {name}")
        print(f"           {line}")
        if rc == 0:
            survivors.append((letter, name))
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if survivors:
        print(f"{len(survivors)} SURVIVOR(S):")
        for letter, name in survivors:
            print(f"  [{letter}] {name}")
        return 1
    print("every wrong default is caught by the suite")
    return 0


if __name__ == "__main__":
    sys.exit(main())
