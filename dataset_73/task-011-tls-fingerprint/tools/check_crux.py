#!/usr/bin/env python3
"""Prove each crux bites: build the wrong-default implementations and show the
test suite rejects them.

A "crux" is only worth anything if the obvious-but-wrong implementation fails.
This script takes the reference engine and rewrites it into the specific wrong
implementations a real engineer would plausibly produce here:

  A  version read from the record header (what the retired v1 doc says)
  B1 reserved (RFC 8701) values passed through unfiltered
  B2 reserved values approximated with a low-byte test, which also eats
     extension 0x000A / group ids ending in 0x0A
  B3 the reserved filter also applied to EC point formats (8-bit values)
  C  extension types sorted ascending instead of kept in wire order
  D  only the first record's payload parsed, ignoring fragmentation
  V1 all of the above at once -- a faithful implementation of
     environment/docs/legacy/dissector-v1.md

For each one it runs the full suite and reports how many tests fail, plus
whether the test named as that crux's sentinel is among the failures. A variant
that passes everything would mean the suite does not depend on that behaviour.

This script does not ship in the task image and contains no answers that are not
already in environment/docs/.
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

FILTER_BLOCK = """        ciphers = [c for c in ciphers if c not in GREASE_VALUES]
        extensions = [e for e in ext_order if e not in GREASE_VALUES]
        curves = [c for c in curves if c not in GREASE_VALUES]
"""

NO_FILTER = """        extensions = list(ext_order)
"""

LOW_BYTE_FILTER = """        ciphers = [c for c in ciphers if c & 0xFF != 0x0A]
        extensions = [e for e in ext_order if e & 0xFF != 0x0A]
        curves = [c for c in curves if c & 0xFF != 0x0A]
"""

FILTER_PLUS_POINT_FORMATS = FILTER_BLOCK + """        point_formats = [p for p in point_formats if p not in GREASE_VALUES
                         and p != 0x0A]
"""

SORTED_EXTENSIONS = """        ciphers = [c for c in ciphers if c not in GREASE_VALUES]
        extensions = sorted(e for e in ext_order if e not in GREASE_VALUES)
        curves = [c for c in curves if c not in GREASE_VALUES]
"""

BODY_VERSION = "        version = _u16(body, 0)"
HEADER_VERSION = "        version = (blob[1] << 8) | blob[2]"

REASSEMBLE = "        hs = self._reassemble(blob)"
FIRST_RECORD_ONLY = "        hs = blob[5:5 + ((blob[3] << 8) | blob[4])]"


def patch(source, *pairs):
    out = source
    for old, new in pairs:
        if old not in out:
            raise SystemExit("check_crux: anchor not found in reference engine:\n  %r"
                             % old[:60])
        out = out.replace(old, new, 1)
    return out


#: (label, crux letter, engine source transform, sentinel test name)
def variants(source):
    return [
        ("A  version from the record header", "A",
         patch(source, (BODY_VERSION, HEADER_VERSION)),
         "test_version_comes_from_handshake_body"),
        ("B1 reserved values passed through", "B",
         patch(source, (FILTER_BLOCK, NO_FILTER)),
         "test_reserved_cipher_suites_are_excluded"),
        ("B2 reserved values matched on the low byte", "B",
         patch(source, (FILTER_BLOCK, LOW_BYTE_FILTER)),
         "test_supported_groups_extension_survives_reserved_filtering"),
        ("B3 reserved filter applied to point formats too", "B",
         patch(source, (FILTER_BLOCK, FILTER_PLUS_POINT_FORMATS)),
         "test_point_formats_are_never_filtered"),
        ("C  extension types sorted ascending", "C",
         patch(source, (FILTER_BLOCK, SORTED_EXTENSIONS)),
         "test_extension_types_keep_wire_order"),
        ("D  only the first record parsed", "D",
         patch(source, (REASSEMBLE, FIRST_RECORD_ONLY)),
         "test_fragment_split_after_compression_methods"),
        ("V1 the retired v1 dissector, faithfully", "ABCD",
         patch(source,
               (BODY_VERSION, HEADER_VERSION),
               (FILTER_BLOCK, SORTED_EXTENSIONS.replace(
                   "sorted(e for e in ext_order if e not in GREASE_VALUES)",
                   "sorted(ext_order)")),
               (REASSEMBLE, FIRST_RECORD_ONLY)),
         "test_corpus_capture_matches_expected[chrome_131]"),
    ]


def run_tests(engine_source, work):
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
        [sys.executable, "-m", "pytest", str(TESTS), "-v", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True, timeout=300)
    outcomes = re.findall(r"::(\S+) (PASSED|FAILED|ERROR)\b", result.stdout)
    failed = [name for name, status in outcomes if status != "PASSED"]
    return len(outcomes), failed


def main():
    source = ENGINE.read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    ok = True
    try:
        total, failed = run_tests(source, work)
        if failed:
            print("BASELINE BROKEN: the reference engine fails %d/%d of its own "
                  "tests. Nothing below would mean anything." % (len(failed), total))
            return 1
        print("baseline: reference engine passes %d/%d\n" % (total, total))

        for label, letter, mutated, sentinel in variants(source):
            total, failed = run_tests(mutated, work)
            caught = len(failed) > 0
            hit = sentinel in failed
            status = "FAILS" if caught else "SURVIVES"
            print("[%s] %-45s %-8s %d/%d tests fail" %
                  (letter, label, status, len(failed), total))
            print("       sentinel %-60s %s" %
                  (sentinel, "fails (good)" if hit else "PASSES (bad)"))
            if not caught or not hit:
                ok = False
        print()
        if ok:
            print("every wrong-default implementation is rejected by the suite, and "
                  "each one is caught by the test named for its crux.")
        else:
            print("at least one wrong-default implementation is not properly caught.")
        return 0 if ok else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
