#!/usr/bin/env python3
"""Prove that each crux in this task actually bites.

A crux is only worth anything if the *plausible wrong answer* fails. This
script builds the wrong answers on purpose and runs the real test suite
against each one.

Two kinds of wrong answer are built:

* ``literal-spec-transcription`` -- the whole engine written from the task
  statement alone, the way a solver who never opened ``environment/`` would
  write it: fixed-width fields, every name spelled out, every value field
  absolute, ``config`` ignored, and 0xFFFF read as a magnitude. This is the
  baseline "no discovery" implementation, and its score is the floor the task
  must sit above.

* one variant per crux, produced by patching a single decision in the
  reference engine. Each isolates exactly one wrong default, so a failure
  points at one rule rather than at a pile of them.

Every variant must score strictly below 1.0, and the literal transcription
must score below the task's pass threshold. The script prints the ladder so a
reviewer can see the reward really is continuous.

This script does not ship in the task image.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
ENGINE = TASK / "solution" / "engine" / "engine.py"
TESTS = TASK / "tests" / "test_outputs.py"
PASS_THRESHOLD = 0.5


LITERAL_TRANSCRIPTION = '''
from __future__ import annotations

import struct


class CustomBinaryEngine:
    """BIN1 exactly as a reader of the task statement would guess it."""

    MAGIC = b"BIN1"

    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def encode(self, recs):
        if len(recs) > 0xFFFF:
            raise ValueError("record count exceeds u16 range")
        out = bytearray()
        out += self.MAGIC
        out += struct.pack("<H", len(recs))
        for r in recs:
            tag = r["tag"]
            value = r["value"]
            name_bytes = r["name"].encode("utf-8")
            if not 0 <= tag <= 0xFF:
                raise ValueError("tag out of u8 range")
            if not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("value out of u32 range")
            if len(name_bytes) > 0xFFFF:
                raise ValueError("name length exceeds u16 range")
            out += struct.pack("<B", tag)
            out += struct.pack("<H", len(name_bytes))
            out += name_bytes
            out += struct.pack("<I", value)
        return bytes(out)

    def decode(self, blob):
        if blob[:4] != self.MAGIC:
            raise ValueError("bad magic")
        if len(blob) < 6:
            raise ValueError("truncated header")
        n = struct.unpack("<H", blob[4:6])[0]
        out = []
        i = 6
        for _ in range(n):
            if i + 3 > len(blob):
                raise ValueError("truncated record header")
            tag = blob[i]
            i += 1
            nlen = struct.unpack("<H", blob[i:i + 2])[0]
            i += 2
            if i + nlen + 4 > len(blob):
                raise ValueError("truncated record body")
            name = blob[i:i + nlen].decode("utf-8")
            i += nlen
            value = struct.unpack("<I", blob[i:i + 4])[0]
            i += 4
            out.append({"tag": tag, "name": name, "value": value})
        return out
'''


#: The intern block as the reference writes it, and the "most recent
#: occurrence" rewrite of it. Kept as whole blocks because the difference is
#: where the table is written, not a single token.
INTERN_FIRST = """            if name_bytes in first_index:
                out += struct.pack("<H", U16_MAX)
                out += struct.pack("<H", first_index[name_bytes])
            else:
                first_index[name_bytes] = index
                out += struct.pack("<H", len(name_bytes))
                out += name_bytes
"""

INTERN_MOST_RECENT = """            if name_bytes in first_index:
                out += struct.pack("<H", U16_MAX)
                out += struct.pack("<H", first_index[name_bytes])
            else:
                out += struct.pack("<H", len(name_bytes))
                out += name_bytes
            first_index[name_bytes] = index
"""


#: (label, crux, [(find, replace), ...]) applied to the reference source.
VARIANTS = [
    ("sentinel-read-as-a-magnitude", "H",
     [("U16_LIMIT = 0xFFFE", "U16_LIMIT = 0xFFFF")]),
    ("streamed-count-read-as-65535-records", "H",
     [("streamed = count == U16_MAX", "streamed = False")]),
    ("back-reference-to-most-recent-occurrence", "D",
     [(INTERN_FIRST, INTERN_MOST_RECENT)]),
    ("back-reference-as-a-distinct-name-ordinal", "D",
     [("first_index[name_bytes] = index",
       "first_index[name_bytes] = len(first_index)")]),
    ("names-repeated-instead-of-interned", "D",
     [("            if name_bytes in first_index:",
       "            if False:")]),
    ("series-chain-keyed-by-tag-alone", "A",
     [("key = (tag, name_bytes)", "key = (tag,)")]),
    ("delta-written-as-twos-complement", "A",
     [("field = _zigzag_encode(delta)", "field = delta & U32_MAX"),
      ("_zigzag_decode(field)", "_to_signed32(field)")]),
    ("delta-computed-in-unbounded-integers", "A",
     [("_to_signed32((value - previous[key]) & U32_MAX)",
       "(value - previous[key])")]),
    ("every-tag-delta-coded", "A",
     [('self.encoding_for(tag, revision) == "delta"', "True")]),
    ("registry-flattened-latest-row-wins", "I",
     [("if row_tag != tag or from_rev > revision:", "if row_tag != tag:")]),
    ("in-band-revision-marker-ignored", "I",
     [("if tag == TAG_REVISION_MARKER:\n                revision = value",
       "if False:\n                revision = value")]),
    ("config-accepted-and-ignored", "I",
     [("        rev = self._options.get(\"registry_revision\")",
       "        rev = None")]),
]


def run_tests(source, work):
    """Run the suite against one engine source; return (passed, total)."""
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(ENGINE.parent, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "engine.py").write_text(source, encoding="utf-8")

    environment = dict(os.environ)
    environment["ENGINE_DIR"] = str(package)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=600)
    text = result.stdout

    def count(pattern):
        found = re.search(pattern, text)
        return int(found.group(1)) if found else 0

    passed = count(r"(\d+) passed")
    failed = count(r"(\d+) failed") + count(r"(\d+) error")
    return passed, passed + failed


def main():
    if not ENGINE.exists():
        print("no reference engine at %s" % ENGINE)
        return 1

    reference = ENGINE.read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    failures = []
    try:
        passed, total = run_tests(reference, work)
        if total == 0 or passed != total:
            print("BASELINE BROKEN: reference scores %d/%d. Nothing below "
                  "would mean anything." % (passed, total))
            return 1
        print("reference engine            %d/%d  score 1.000" % (passed, total))
        print()

        passed, total = run_tests(LITERAL_TRANSCRIPTION, work)
        score = passed / total if total else 0.0
        print("literal-spec-transcription  %d/%d  score %.3f  (no discovery)"
              % (passed, total, score))
        if score >= PASS_THRESHOLD:
            failures.append(
                "the literal transcription scores %.3f, at or above the %.2f "
                "pass threshold -- the task does not discriminate"
                % (score, PASS_THRESHOLD))
        print()

        for label, crux, patches in VARIANTS:
            source = reference
            for find, replace in patches:
                if find not in source:
                    failures.append("variant %r: pattern not found in the "
                                    "reference engine: %r" % (label, find))
                    source = None
                    break
                source = source.replace(find, replace)
            if source is None:
                continue
            passed, total = run_tests(source, work)
            score = passed / total if total else 0.0
            status = "caught" if score < 1.0 else "SURVIVOR"
            print("  [%s] %-42s %2d/%d  score %.3f  %s"
                  % (crux, label, passed, total, score, status))
            if score >= 1.0:
                failures.append(
                    "variant %r passes the whole suite: no test depends on "
                    "that rule" % label)

        print()
        if failures:
            for message in failures:
                print("FAIL: %s" % message)
            return 1
        print("OK: every wrong-default implementation is caught, and the "
              "no-discovery baseline scores below the pass threshold.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
