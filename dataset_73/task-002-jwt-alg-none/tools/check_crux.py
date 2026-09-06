#!/usr/bin/env python3
"""Prove each crux actually bites, by building the wrong implementation.

`check_mutations.py` damages the reference at random to show the tests are not
vacuous. This script is narrower and more pointed: for every crux the task is
built around, it rewrites the reference into the *plausible mistake* -- the
reading a competent engineer arrives at from the instruction alone, or from
the stale triage tool that ships in the image -- and runs the real suite
against it.

  BITES      at least one test failed  -> the crux is load-bearing
  NO EFFECT  every test still passed   -> the suite does not distinguish the
                                          wrong default from the right answer,
                                          which means the crux is decorative

Each variant is a small, named, single-site rewrite of
`solution/engine/engine.py`, so the "wrong default" being claimed is visible in
this file rather than asserted. No secrets, no test answers: the variants are
derived mechanically from the reference at run time.

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
STUB = TASK / "environment" / "engine" / "engine.py"
TESTS = TASK / "tests" / "test_outputs.py"


# --------------------------------------------------------------------------
# The wrong defaults. Each entry is (crux, label, why, [(find, replace), ...]).
# `find` must occur exactly once in the reference or the variant is reported as
# broken rather than silently skipped.
# --------------------------------------------------------------------------
VARIANTS = [
    (
        "I", "keyring/verify-with-the-current-key",
        "Look the ring up by 'what is in force now' instead of by the token's "
        "iat. Every pre-rotation token breaks -- which is the entire reason "
        "the ring exists.",
        [(
            '            secret = self._lookup(kid, iat)["secret"]',
            '            _current = self._active_entry(self._now())\n'
            '            if _current is None:\n'
            '                raise UnauthorizedError("unknown_kid", "nothing in force")\n'
            '            secret = _current["secret"]',
        )],
    ),
    (
        "I", "keyring/trust-the-kid",
        "Accept any secret that is present on the ring for that kid, whatever "
        "its window. This is the production vulnerability: a leaked retired "
        "secret mints a fresh token and it verifies.",
        [(
            "            if self._in_window(entry, iat):",
            "            if True:",
        )],
    ),
    (
        "I", "keyring/dict-keyed-by-kid",
        "The near-universal idiom `{e['kid']: e for e in ring}`. It silently "
        "collapses the kid that was rolled back and re-activated, so one of "
        "its two windows disappears.",
        [(
            "        matched = False\n        for entry in self._keyring:",
            "        matched = False\n"
            '        for entry in {e["kid"]: e for e in self._keyring}.values():',
        )],
    ),
    (
        "B", "alg/case-insensitive-pin",
        "The tidy-up after seeing 'NONE' rejected: normalise both sides of the "
        "pin comparison too. That accepts alg='hs256' -- the algorithm-"
        "confusion bypass the gateway exists to stop.",
        [(
            "        if alg != self._alg:",
            "        if str(alg).lower() != self._alg.lower():",
        )],
    ),
    (
        "B", "alg/str-coercion-makes-null-none",
        "`str(hdr.get('alg','')).lower() == 'none'`, which classifies a JSON "
        "null alg as the unsigned algorithm instead of a pin mismatch.",
        [(
            "        if isinstance(alg, str) and alg.strip().casefold() in _NEVER_ACCEPT:",
            "        if str(alg).strip().casefold() in _NEVER_ACCEPT:",
        )],
    ),
    (
        "B", "alg/digest-hard-coded-to-sha256",
        "Keep hashlib.sha256 wired in regardless of the pin, so an HS384 pin "
        "issues a token whose header lies about its own MAC.",
        [(
            "    return _DIGESTS[alg]",
            "    return hashlib.sha256",
        )],
    ),
    (
        "B", "configure/adopt-any-pin",
        "Take whatever algorithm a config push names. A bad push then takes "
        "the gateway down instead of being logged and survived.",
        [(
            '        if "alg" in options and options["alg"] in _DIGESTS:',
            '        if "alg" in options:',
        )],
    ),
    (
        "C", "codes/from-the-triage-tool",
        "Mine tools/jwt_triage.py for the reason table, as its docstring "
        "invites. Expired and unknown-kid become ValidationError, and the "
        "algorithm-pin rejection is filed as a signature failure.",
        [
            ('            raise UnauthorizedError("expired", "token is past its exp")',
             '            raise ValidationError("expired", "token is past its exp")'),
            ('            raise UnauthorizedError("unknown_kid", "no ring entry named %r" % (kid,))',
             '            raise ValidationError("unknown_kid", "no ring entry named %r" % (kid,))'),
            ('                raise UnauthorizedError("unknown_kid", "header carries no kid")',
             '                raise ValidationError("unknown_kid", "header carries no kid")'),
            ('            raise UnauthorizedError("alg_pin_mismatch", "header alg is not the pin")',
             '            raise UnauthorizedError("sig_mismatch", "header alg is not the pin")'),
        ],
    ),
    (
        "H", "skew/one-leeway-everywhere",
        "Having found the key-window tolerance, hoist it into one constant and "
        "apply it to every timestamp comparison. That quietly grants every "
        "expired token another minute of life.",
        [(
            "        if isinstance(exp, (int, float)) and not isinstance(exp, bool) and exp < now:",
            "        if isinstance(exp, (int, float)) and not isinstance(exp, bool) and exp + LEEWAY < now:",
        )],
    ),
    (
        "H", "skew/no-leeway-at-all",
        "Compare iat strictly against the activation instant. The classic "
        "post-rotation outage: legitimate tokens from a slightly slow node "
        "are refused.",
        [(
            '        started = entry["activated"] - LEEWAY',
            '        started = entry["activated"]',
        )],
    ),
    (
        "*", "combined/straight-from-the-spec",
        "Everything at once: the reading you get from the instruction plus the "
        "triage tool, with none of the environment/ evidence opened.",
        [
            ("            if self._in_window(entry, iat):", "            if True:"),
            ("        if alg != self._alg:",
             "        if str(alg).lower() != self._alg.lower():"),
            ("        if isinstance(alg, str) and alg.strip().casefold() in _NEVER_ACCEPT:",
             "        if str(alg).strip().casefold() in _NEVER_ACCEPT:"),
            ("    return _DIGESTS[alg]", "    return hashlib.sha256"),
            ('            raise UnauthorizedError("expired", "token is past its exp")',
             '            raise ValidationError("expired", "token is past its exp")'),
        ],
    ),
]


def apply_patches(source, patches):
    out = source
    for find, replace in patches:
        count = out.count(find)
        if count != 1:
            raise LookupError("anchor occurs %d times, expected 1:\n%s"
                              % (count, find))
        out = out.replace(find, replace)
    if out == source:
        raise LookupError("patch set changed nothing")
    return out


def run_tests(engine_source, work, package_source=None):
    """Run the suite against an engine package holding `engine_source`.

    Returns (returncode, list of failing test ids).
    """
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree((package_source or ENGINE.parent), package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "engine.py").write_text(engine_source, encoding="utf-8")

    environment = dict(os.environ)
    environment["ENGINE_DIR"] = str(package)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=600)
    failing = sorted(set(re.findall(r"^FAILED [^:]+::(\S+)", result.stdout,
                                    re.MULTILINE)))
    return result.returncode, failing, result.stdout


def summarise(failing, limit=6):
    shown = failing[:limit]
    tail = "" if len(failing) <= limit else " (+%d more)" % (len(failing) - limit)
    return ", ".join(shown) + tail


def main():
    if not ENGINE.exists():
        print("no reference engine at %s" % ENGINE)
        return 1

    source = ENGINE.read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    problems = []
    try:
        code, failing, out = run_tests(source, work)
        if code != 0:
            print("BASELINE BROKEN: the reference engine fails its own tests.")
            print(out[-2000:])
            return 1
        print("baseline: reference engine passes the suite\n")

        for crux, label, why, patches in VARIANTS:
            try:
                variant = apply_patches(source, patches)
            except LookupError as exc:
                print("[%s] %-38s BROKEN PATCH -- %s" % (crux, label, exc))
                problems.append(label)
                continue
            code, failing, _ = run_tests(variant, work)
            if failing:
                print("[%s] %-38s BITES     %d failing: %s"
                      % (crux, label, len(failing), summarise(failing)))
            else:
                print("[%s] %-38s NO EFFECT -- the suite cannot tell this "
                      "apart from the reference" % (crux, label))
                problems.append(label)
            print("      %s" % why.replace("\n", " "))

        print()
        if STUB.exists():
            code, failing, out = run_tests(
                STUB.read_text(encoding="utf-8"), work,
                package_source=STUB.parent)
            passed = re.search(r"(\d+) passed", out)
            print("starting stub: %d tests failing, %s passing"
                  % (len(failing), passed.group(1) if passed else "0"))
            if passed:
                problems.append("stub passes %s tests" % passed.group(1))

        print()
        if problems:
            print("PROBLEMS: %s" % "; ".join(problems))
            return 1
        print("every wrong default is caught by the suite")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
