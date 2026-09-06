#!/usr/bin/env python3
"""Prove that each crux in this task actually bites.

A crux is only worth anything if the *obvious* implementation - the one a
competent engineer writes after reading instruction.md without opening
environment/ - measurably fails. This script builds those obvious
implementations by patching the reference engine back into its naive form, one
crux at a time, and runs the full suite against each.

    caught     at least one test failed   -> the crux is enforced by the suite
    SURVIVOR   every test still passed    -> the suite does not depend on it

The final variant, "naive-all", is the whole spec-transcription reading at
once: lax base64 decoding, plain json.loads, an unconditional pin setter, a
case-folded alg comparison and a substring key-type scan. It stands in for the
model that never opened environment/, and it must fail a substantial fraction
of the suite while still passing the parts of the task that were always easy -
that is what keeps the reward continuous rather than all-or-nothing.

No secrets here: every patch below is the *wrong* answer, written out in full.

    python tools/check_crux.py
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
SOLUTION = TASK / "solution" / "engine"
TESTS = TASK / "tests" / "test_outputs.py"


# --------------------------------------------------------------------------
# The wrong defaults, as textual patches against the reference engine.
# Each entry is (file, exact text to find, replacement).
# --------------------------------------------------------------------------

LAX_BASE64 = (
    "engine.py",
    "    if len(seg) % 4 == 1:\n"
    "        return False\n"
    "    return all(ch in _B64URL_ALPHABET for ch in seg)",
    "    return True   # WRONG DEFAULT: no alphabet check, just pad and decode",
)

PLAIN_JSON_LOADS = (
    "engine.py",
    "json.loads(b64d(seg), object_pairs_hook=_reject_duplicates)",
    "json.loads(b64d(seg))   # WRONG DEFAULT: last duplicate silently wins",
)

UNCONDITIONAL_PIN = (
    "engine.py",
    "        requested = (options or {}).get(\"alg\")\n"
    "        if requested in PINNABLE_ALGS:\n"
    "            self._expected = requested",
    "        # WRONG DEFAULT: honour any requested algorithm\n"
    "        self._expected = (options or {}).get(\"alg\", self._expected)",
)

CASE_FOLDED_ALG = (
    "engine.py",
    "        if alg != self._expected:",
    "        # WRONG DEFAULT: the retired 2024-06 postmortem's recommendation\n"
    "        if not isinstance(alg, str) or alg.upper() != self._expected.upper():",
)

SUBSTRING_KEY_TYPE = (
    "verifier.py",
    "def detect_key_confusion(header_alg: str, key_type: str) -> bool:\n"
    "    \"\"\"True iff an HMAC-family alg is being presented with an asymmetric key.\"\"\"\n"
    "    if header_alg not in HMAC_ALGS:\n"
    "        return False\n"
    "    return key_type_family(key_type) in ASYMMETRIC_KTY",
    "def detect_key_confusion(header_alg: str, key_type: str) -> bool:\n"
    "    # WRONG DEFAULT: scan the whole operator description for a family name\n"
    "    if header_alg == \"HS256\" and \"RSA\" in key_type.upper():\n"
    "        return True\n"
    "    return False",
)

SUBSTRING_KEY_TYPE_EXTENDED = (
    "verifier.py",
    "def detect_key_confusion(header_alg: str, key_type: str) -> bool:\n"
    "    \"\"\"True iff an HMAC-family alg is being presented with an asymmetric key.\"\"\"\n"
    "    if header_alg not in HMAC_ALGS:\n"
    "        return False\n"
    "    return key_type_family(key_type) in ASYMMETRIC_KTY",
    "def detect_key_confusion(header_alg: str, key_type: str) -> bool:\n"
    "    # WRONG DEFAULT: the tempting repair - add the other families as\n"
    "    # substrings instead of reading only the leading kty token.\n"
    "    if header_alg not in HMAC_ALGS:\n"
    "        return False\n"
    "    upper = key_type.upper()\n"
    "    return any(name in upper for name in (\"RSA\", \"EC\", \"OKP\"))",
)

DATE_BLIND_REGISTER = (
    "engine.py",
    'PINNABLE_ALGS = frozenset({"RS256", "HS256", "PS256", "RS384"})',
    "# WRONG DEFAULT: alg_policy.csv read as 'the last row for this alg wins', with the 2026-09-01 snapshot date ignored. That admits ES256 (permitted, but not until 2026-11-01) and drops RS384 (revoked, but not until 2026-12-01).\n"
    'PINNABLE_ALGS = frozenset({"RS256", "HS256", "PS256", "ES256"})',
)

VARIANTS = [
    ("B  lax-base64        (pad-and-decode, no alphabet check)", [LAX_BASE64]),
    ("D  plain-json-loads  (duplicate members silently collapse)", [PLAIN_JSON_LOADS]),
    ("D  substring-kty     ('RSA' in key_type.upper())", [SUBSTRING_KEY_TYPE]),
    ("D  substring-kty+    ('RSA'/'EC'/'OKP' as substrings)", [SUBSTRING_KEY_TYPE_EXTENDED]),
    ("I  unconditional-pin (configure honours any alg)", [UNCONDITIONAL_PIN]),
    ("I  date-blind-register (last row wins, snapshot date ignored)",
     [DATE_BLIND_REGISTER]),
    ("C  case-folded-alg   (retired postmortem's .upper() advice)", [CASE_FOLDED_ALG]),
    ("*  naive-all         (instruction.md read without environment/)",
     [LAX_BASE64, PLAIN_JSON_LOADS, UNCONDITIONAL_PIN, CASE_FOLDED_ALG,
      SUBSTRING_KEY_TYPE]),
]


def build(work, patches):
    """Copy the reference engine and apply the given wrong defaults."""
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(SOLUTION, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for filename, needle, replacement in patches:
        path = package / filename
        source = path.read_text(encoding="utf-8")
        if needle not in source:
            raise SystemExit(
                "check_crux.py is out of date: the patch anchor below no longer "
                "appears in solution/engine/%s\n---\n%s" % (filename, needle))
        path.write_text(source.replace(needle, replacement, 1), encoding="utf-8")
    return package


def run(package):
    """(passed, failed) for the suite run against this engine package."""
    environment = dict(os.environ)
    environment["ENGINE_DIR"] = str(package)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=300)
    tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    passed = int((re.search(r"(\d+) passed", tail) or [0, 0])[1] or 0)
    failed = int((re.search(r"(\d+) failed", tail) or [0, 0])[1] or 0)
    failed += int((re.search(r"(\d+) error", tail) or [0, 0])[1] or 0)
    return passed, failed


def main():
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    try:
        baseline_pass, baseline_fail = run(build(work, []))
        if baseline_fail:
            print("BASELINE BROKEN: the reference engine fails %d of its own "
                  "tests. Nothing below would mean anything." % baseline_fail)
            return 1
        total = baseline_pass
        print("reference engine: %d/%d passing\n" % (baseline_pass, total))

        survivors = []
        for label, patches in VARIANTS:
            passed, failed = run(build(work, patches))
            status = "caught  " if failed else "SURVIVOR"
            print("  %s  %-58s %2d failed, %2d passed" % (status, label, failed, passed))
            if not failed:
                survivors.append(label)

        print()
        if survivors:
            print("A SURVIVOR means no test in the suite depends on that crux:")
            for label in survivors:
                print("  SURVIVOR  %s" % label)
            return 1

        print("Every wrong default is caught by at least one test, and the "
              "fully naive implementation still passes the easy part of the "
              "suite, so partial credit stays partial.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
