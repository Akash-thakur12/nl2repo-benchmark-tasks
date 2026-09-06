#!/usr/bin/env python3
"""Prove each crux bites: implement the wrong default, watch the suite reject it.

For every crux this task plants, there is a plausible "obvious" reading that the
old specification, a retired note, or an on-call script actively steers a reader
toward. This script builds a whole engine for each wrong reading, runs the full
behaviour suite against it, and asserts two things:

  1. the wrong engine FAILS at least one test (the crux is graded), and
  2. it still PASSES all 8 legacy tests (reward stays continuous -- a wrong
     reading of the new mechanism does not zero the score).

It also confirms the reference engine passes everything. This script ships no
secrets; every wrong engine is derived from the reference by a small edit
described in its label.

Run: python tools/check_crux.py
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

LEGACY_TESTS = [
    "test_sign_verify_roundtrip",
    "test_sign_is_deterministic",
    "test_str_key_is_utf8_encoded_same_as_bytes",
    "test_truncation_length_follows_config",
    "test_recover_key_from_samples",
    "test_recover_key_returns_none_when_no_candidate_matches",
    "test_recover_key_without_samples_returns_none",
    "test_reset_and_configure_clear_samples",
]


def _sub(source, old, new, label):
    if old not in source:
        raise SystemExit("check_crux: anchor not found for %r" % label)
    return source.replace(old, new, 1)


# --- Crux I: use the current top-level mac_bytes, ignore width_history. ------
def wrong_crux_1(source):
    """tag_width_at returns the key's current mac_bytes, ignoring history.

    This is the INC-4417 audit-worker bug and what RETIRED-tag-width-note.md
    tells you to do.
    """
    body = (
        "    def tag_width_at(self, kid, ts):\n"
        "        row = self._index.get(kid)\n"
        "        if row is None:\n"
        "            return None\n"
        "        return row[\"mac_bytes\"]\n"
    )
    return re.sub(r"    def tag_width_at\(self, kid, ts\):\n(?:.*\n)*?        return width\n",
                  body, source, count=1)


# --- Crux II: trim trailing zeros and compare at the trimmed length. ---------
def wrong_crux_2(source):
    """audit trims the pad off with rstrip and compares at that length.

    This is exactly tag_doctor.py's model: it waves the padded forgery through.
    """
    old = (
        "        frame = self._frame(record.get(\"tag_hex\"))\n"
        "        if frame is None or any(frame[width:]):\n"
        "            return \"malformed\"\n"
        "        expected = hmac.new(secret, self._message(record),\n"
        "                            hashlib.sha256).digest()[:width]\n"
        "        return \"ok\" if hmac.compare_digest(expected, frame[:width]) else \"bad-tag\"\n"
    )
    new = (
        "        try:\n"
        "            raw = bytes.fromhex(record.get(\"tag_hex\"))\n"
        "        except Exception:\n"
        "            return \"malformed\"\n"
        "        trimmed = raw.rstrip(b\"\\x00\")\n"
        "        w = len(trimmed)\n"
        "        expected = hmac.new(secret, self._message(record),\n"
        "                            hashlib.sha256).digest()[:w]\n"
        "        return \"ok\" if hmac.compare_digest(expected, trimmed) else \"bad-tag\"\n"
    )
    return _sub(source, old, new, "crux 2")


# --- Crux III: return the first matching candidate (the deleted clause). -----
def wrong_crux_3(source):
    """recover_key returns the first candidate that matches, per the old spec.

    On the 2-octet ambiguous evidence set it returns a key where the answer is
    None.
    """
    old = (
        "        matches = self.matching_keys(candidates)\n"
        "        if not matches:\n"
        "            return None\n"
        "        materials = {_as_bytes(match) for match in matches}\n"
        "        if len(materials) != 1:\n"
        "            return None\n"
        "        return materials.pop()\n"
    )
    new = (
        "        matches = self.matching_keys(candidates)\n"
        "        return _as_bytes(matches[0]) if matches else None\n"
    )
    return _sub(source, old, new, "crux 3")


# --- Crux III (other direction): unique iff exactly one list element. --------
def wrong_crux_3b(source):
    """recover_key demands exactly one matched listing.

    Fixes the first-match bug the wrong way: now the duplicated-regional-secret
    job returns None where the answer is the key.
    """
    old = (
        "        matches = self.matching_keys(candidates)\n"
        "        if not matches:\n"
        "            return None\n"
        "        materials = {_as_bytes(match) for match in matches}\n"
        "        if len(materials) != 1:\n"
        "            return None\n"
        "        return materials.pop()\n"
    )
    new = (
        "        matches = self.matching_keys(candidates)\n"
        "        return _as_bytes(matches[0]) if len(matches) == 1 else None\n"
    )
    return _sub(source, old, new, "crux 3b")


WRONG = [
    ("crux I: current mac_bytes, ignore width_history", wrong_crux_1),
    ("crux II: rstrip the pad, compare at trimmed length", wrong_crux_2),
    ("crux III: return the first matching candidate", wrong_crux_3),
    ("crux III: unique iff exactly one matched listing", wrong_crux_3b),
]


def run(engine_source, work, tests=None):
    """Return (passed, failed, failed_names) for a run of the suite."""
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(ENGINE.parent, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "engine.py").write_text(engine_source, encoding="utf-8")
    env = dict(os.environ)
    env["ENGINE_DIR"] = str(package)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
           "-p", "no:cacheprovider"]
    if tests:
        cmd += ["-k", " or ".join(tests)]
    result = subprocess.run(cmd, cwd=str(TASK), env=env,
                            capture_output=True, text=True, timeout=300)
    passed = len(re.findall(r"\bPASSED\b", result.stdout))
    # -q prints dots, not names; parse the summary line and the FAILED lines.
    failed_names = re.findall(r"::([\w\[\]@:.\-]+) FAILED", result.stdout)
    m_pass = re.search(r"(\d+) passed", result.stdout)
    m_fail = re.search(r"(\d+) failed", result.stdout)
    npass = int(m_pass.group(1)) if m_pass else 0
    nfail = int(m_fail.group(1)) if m_fail else 0
    fnames = re.findall(r"FAILED [^:]*::([\w\[\]@:.\-]+)", result.stdout)
    return npass, nfail, fnames


def main():
    if not ENGINE.exists():
        print("no reference engine at %s" % ENGINE)
        return 1
    source = ENGINE.read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    ok = True
    try:
        npass, nfail, _ = run(source, work)
        if nfail:
            print("BASELINE BROKEN: reference engine fails %d tests" % nfail)
            return 1
        print("reference engine: %d passed, 0 failed" % npass)
        print()

        for label, mutate in WRONG:
            mutated = mutate(source)
            if mutated == source:
                print("  ERROR    %s -- mutation was a no-op" % label)
                ok = False
                continue
            npass, nfail, fnames = run(mutated, work)
            legacy_fail = [n for n in fnames
                           if any(n.startswith(t) for t in LEGACY_TESTS)]
            caught = nfail > 0
            legacy_green = not legacy_fail
            status = "caught " if (caught and legacy_green) else "PROBLEM"
            print("  %s %s" % (status, label))
            print("             -> %d failed, %d passed; legacy tests green: %s"
                  % (nfail, npass, legacy_green))
            if not caught:
                print("             !! no test failed: this crux is not graded")
                ok = False
            if not legacy_green:
                print("             !! legacy tests broke: reward not continuous: %s"
                      % legacy_fail)
                ok = False
        print()
        print("OK: every wrong default is caught and the legacy suite stays green."
              if ok else "FAIL: see the PROBLEM lines above.")
        return 0 if ok else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
