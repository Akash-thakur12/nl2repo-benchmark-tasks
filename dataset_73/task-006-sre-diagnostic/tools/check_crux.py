#!/usr/bin/env python3
"""Prove each crux bites, by implementing the wrong default and watching it fail.

A crux is only worth anything if the plausible-but-wrong reading of the
environment actually loses points. This script builds a family of rival engines
- each one the reference with exactly one crux read the wrong way - runs the
full behaviour suite against every one of them, and asserts that every rival
fails at least one test.

It also reports, per rival, which tests caught it. That is the evidence a
reviewer wants: it shows the suite is layered (a rival that gets three cruxes
right and one wrong still banks the tests for the three) rather than
all-or-nothing.

Rivals implemented:

  baseline-today      the implementation this task shipped before the redesign
  arrival-order       endpoints taken from the arrival buffer, not sorted by t
  first-write-wins    duplicate timestamps keep the FIRST copy, not the latest
  naive-guards        guards on the raw arrival buffer, no minimum span
  no-span-guard       no 30-second minimum-span admissibility check
  raw-delta           counters read as last-minus-first, no reset recovery
  drop-reset-step     reset detected but the decreasing step is skipped
  no-rate-norm        counter thresholds compared against raw window totals
  newest-policy       always the newest threshold revision
  oldest-policy       always the original (r1) threshold revision
  policy-at-end       revision in force at the window END, not its start
  inclusive-span      span guard written as <= 30 instead of < 30
  always-secondary    MEM_PRESSURE always carries secondary: GC_PRESSURE
  const-cpu-suspect   NET_SATURATION emits the constant False for cpu_suspect
  triage-tool         the legacy environment/tools/triage_report.py logic

This script does not ship in the task image.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
REFERENCE = TASK / "solution" / "engine" / "engine.py"
TESTS = TASK / "tests" / "test_outputs.py"


def _sub(src, pattern, replacement, *, count=1, flags=0):
    out, n = re.subn(pattern, replacement, src, count=count, flags=flags)
    if n != count:
        raise SystemExit(
            f"check_crux.py is out of date with the reference engine: "
            f"pattern {pattern!r} matched {n} times, expected {count}"
        )
    return out


# --- window reconstruction (crux E/H) --------------------------------------

def rival_arrival_order(src):
    """Endpoints straight off the arrival buffer, exactly as the retired
    runbook says: "take the first sample delivered and the last delivered"."""
    return _sub(src,
                r"        return \[by_t\[k\] for k in sorted\(by_t\)\]",
                "        return list(self._samples)")


def rival_first_write_wins(src):
    """Duplicate timestamps keep the first copy received rather than the
    superseding retransmit."""
    return _sub(src,
                r"            by_t\[sample\[\"t\"\]\] = sample.*",
                '            by_t.setdefault(sample["t"], sample)')


def rival_naive_guards(src):
    """Both admissibility guards read the way an implementer writes them
    without the runbook: count the raw samples ingested rather than the
    distinct timestamps of the reconstructed window, and no minimum span at
    all. Note that the two guards have to be broken together to be
    distinguishable -- with the span check in place, a window with a single
    distinct timestamp has span 0 and is rejected anyway, so a raw count on
    its own is behaviourally equivalent to the reference."""
    src = _sub(src,
               r"        if len\(window\) < 2:",
               "        if len(self._samples) < 2:")
    return _sub(src, r"MIN_SPAN_SECONDS = 30\.0", "MIN_SPAN_SECONDS = 0.0")


def rival_no_span_guard(src):
    """No minimum-span admissibility check at all."""
    return _sub(src, r"MIN_SPAN_SECONDS = 30\.0", "MIN_SPAN_SECONDS = 0.0")


def rival_inclusive_span(src):
    """Span guard written inclusively, rejecting an exactly-30-second window."""
    return _sub(src,
                r"        if span < MIN_SPAN_SECONDS:",
                "        if span <= MIN_SPAN_SECONDS:")


# --- counters and rates (crux B/D) -----------------------------------------

def rival_raw_delta(src):
    """Counters read as a plain last-minus-first difference: no reset
    recovery. This is the stale comment at the top of triage_report.py."""
    return _sub(src,
                r"    total = 0\.0\n(?:.*\n)*?    return total",
                "    return window[-1][field] - window[0][field]")


def rival_drop_reset_step(src):
    """Reset detected, but the decreasing step is skipped instead of
    contributing the post-restart reading."""
    return _sub(src,
                r"        total \+= \(hi - lo\) if hi >= lo else hi",
                "        total += (hi - lo) if hi >= lo else 0.0")


def rival_no_rate_norm(src):
    """Counter thresholds compared against the raw window total rather than a
    per-minute rate. Invisible on any 60-second window."""
    return _sub(src,
                r"            field: _counter_total\(window, field\) \* 60\.0 / span",
                "            field: _counter_total(window, field)")


# --- threshold policy (crux I) ---------------------------------------------

def _policy_body(expr):
    return (r"    chosen = POLICY_REVISIONS\[0\]\n(?:.*\n)*?    return chosen",
            f"    return {expr}")


def rival_newest_policy(src):
    """Read the dated table as ordinary config and compile in the last row."""
    return _sub(src, *_policy_body("POLICY_REVISIONS[-1]"))


def rival_oldest_policy(src):
    """Scrape the numbers off the retired v1 runbook and never notice the
    table is dated at all."""
    return _sub(src, *_policy_body("POLICY_REVISIONS[0]"))


def rival_policy_at_end(src):
    """Select the revision in force when the window CLOSED rather than when it
    opened. Only diverges on a window that straddles a boundary."""
    src = _sub(src,
               r'        policy = _policy_for\(window\[0\]\["t"\]\)',
               '        policy = _policy_for(window[-1]["t"])')
    return src


# --- verdict payloads (crux H) ---------------------------------------------

def rival_always_secondary(src):
    return _sub(src,
                r"            if gc_hot:\n                verdict\[\"secondary\"\] = \"GC_PRESSURE\"",
                '            verdict["secondary"] = "GC_PRESSURE"')


def rival_const_cpu_suspect(src):
    return _sub(src,
                r'return \{"cause": "NET_SATURATION", "cpu_suspect": bool\(cpu_hot\)\}',
                'return {"cause": "NET_SATURATION", "cpu_suspect": False}')


# --- whole-file rivals ------------------------------------------------------

BASELINE_TODAY = '''
from __future__ import annotations

DISK_DELTA = 100.0
GC_DELTA = 200.0
CPU_HOT = 80.0
CPU_BOTTLENECK = 90.0
CPU_JUMP = 30.0
MEM_HOT = 90.0


class SreDiagEngine:
    def __init__(self, config=None):
        self._samples = []

    def reset(self):
        self._samples = []

    def configure(self, options):
        self._samples = []

    def add(self, t, cpu, mem, disk, net, gc):
        self._samples.append(
            {"t": t, "cpu": cpu, "mem": mem, "disk": disk, "net": net, "gc": gc})

    def diagnose(self):
        if len(self._samples) < 2:
            return {"cause": "INSUFFICIENT_DATA"}
        a, b = self._samples[0], self._samples[-1]
        if (b["disk"] - a["disk"] > DISK_DELTA and b["gc"] - a["gc"] > GC_DELTA
                and b["cpu"] > CPU_HOT):
            return {"cause": "DISK_IO_SATURATION", "secondary": "GC_PRESSURE",
                    "cpu_suspect": False}
        if b["cpu"] > CPU_BOTTLENECK and (b["cpu"] - a["cpu"]) > CPU_JUMP:
            return {"cause": "CPU_BOTTLENECK"}
        if b["mem"] > MEM_HOT:
            return {"cause": "MEM_PRESSURE"}
        return {"cause": "NO_FAULT"}
'''

TRIAGE_TOOL = '''
from __future__ import annotations

# Mirrors environment/tools/triage_report.py: arrival-order endpoints, raw
# last-minus-first counter deltas, and the newest threshold revision.
DISK, GC, NET = 60, 120, 300
CPU_HOT, CPU_BN, CPU_JUMP, MEM_HOT = 75, 88, 20, 88


class SreDiagEngine:
    def __init__(self, config=None):
        self._samples = []

    def reset(self):
        self._samples = []

    def configure(self, options):
        self._samples = []

    def add(self, t, cpu, mem, disk, net, gc):
        self._samples.append(
            {"t": t, "cpu": cpu, "mem": mem, "disk": disk, "net": net, "gc": gc})

    def diagnose(self):
        if len(self._samples) < 2:
            return {"cause": "INSUFFICIENT_DATA"}
        a, b = self._samples[0], self._samples[-1]
        disk, net, gc = b["disk"] - a["disk"], b["net"] - a["net"], b["gc"] - a["gc"]
        if disk > DISK and gc > GC and b["cpu"] > CPU_HOT:
            return {"cause": "DISK_IO_SATURATION", "secondary": "GC_PRESSURE",
                    "cpu_suspect": False}
        if net > NET:
            return {"cause": "NET_SATURATION", "cpu_suspect": b["cpu"] > CPU_HOT}
        if b["cpu"] > CPU_BN and (b["cpu"] - a["cpu"]) > CPU_JUMP:
            return {"cause": "CPU_BOTTLENECK"}
        if b["mem"] > MEM_HOT:
            return {"cause": "MEM_PRESSURE"}
        return {"cause": "NO_FAULT"}
'''

RIVALS = [
    ("baseline-today", lambda src: BASELINE_TODAY,
     "the pre-redesign reference: no ordering, no resets, no rates, no policy"),
    ("triage-tool", lambda src: TRIAGE_TOOL,
     "mirrors the legacy on-call script that ships in environment/tools/"),
    ("arrival-order", rival_arrival_order, "crux E: endpoints off the arrival buffer"),
    ("first-write-wins", rival_first_write_wins, "crux E: retransmit does not supersede"),
    ("naive-guards", rival_naive_guards,
     "crux E: guards on the raw arrival buffer, no minimum span"),
    ("no-span-guard", rival_no_span_guard, "crux E: no 30s minimum span"),
    ("inclusive-span", rival_inclusive_span, "crux E: span guard off by the boundary"),
    ("raw-delta", rival_raw_delta, "crux D: no counter-reset recovery"),
    ("drop-reset-step", rival_drop_reset_step, "crux D: restart step skipped, not credited"),
    ("no-rate-norm", rival_no_rate_norm, "crux B: raw totals instead of per-minute rates"),
    ("newest-policy", rival_newest_policy, "crux I: newest threshold revision"),
    ("oldest-policy", rival_oldest_policy, "crux I: original threshold revision"),
    ("policy-at-end", rival_policy_at_end, "crux I: revision in force at window end"),
    ("always-secondary", rival_always_secondary, "crux H: MEM always claims GC_PRESSURE"),
    ("const-cpu-suspect", rival_const_cpu_suspect, "crux H: NET copies the cascade constant"),
]


def run_suite(engine_source):
    """Run tests/test_outputs.py against one engine source. Returns
    (passed, total, [failed test names])."""
    with tempfile.TemporaryDirectory() as tmp:
        pkg = pathlib.Path(tmp) / "engine"
        pkg.mkdir()
        shutil.copy(TASK / "solution" / "engine" / "__init__.py", pkg / "__init__.py")
        (pkg / "engine.py").write_text(engine_source, encoding="utf-8")

        env = {**_base_env(), "ENGINE_DIR": str(pkg)}
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(TESTS), "-v", "--tb=no"],
            capture_output=True, text=True, env=env, cwd=str(TASK),
        )
        names = re.findall(r"::(\w+) (PASSED|FAILED|ERROR)\b", proc.stdout)
        passed = [n for n, s in names if s == "PASSED"]
        failed = [n for n, s in names if s != "PASSED"]
        if not names:
            raise SystemExit(f"pytest produced no results:\n{proc.stdout}\n{proc.stderr}")
        return len(passed), len(names), failed


def _base_env():
    import os
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


def main():
    reference = REFERENCE.read_text(encoding="utf-8")

    ref_passed, ref_total, ref_failed = run_suite(reference)
    print(f"reference            {ref_passed}/{ref_total} passed")
    if ref_failed:
        print("  FAIL: the reference implementation does not pass its own suite:")
        for name in ref_failed:
            print(f"    {name}")
        return 1
    print()

    survivors = []
    for label, mutate, why in RIVALS:
        passed, total, failed = run_suite(mutate(reference))
        status = "caught  " if failed else "SURVIVOR"
        print(f"{status} {label:<20} {passed}/{total} passed  -- {why}")
        for name in failed[:4]:
            print(f"           caught by: {name}")
        if len(failed) > 4:
            print(f"           ... and {len(failed) - 4} more")
        if not failed:
            survivors.append(label)
        print()

    if survivors:
        print("SURVIVORS - these wrong readings cost nothing and the crux does "
              "not bite:")
        for label in survivors:
            print(f"  {label}")
        return 1

    print(f"OK: all {len(RIVALS)} wrong-default implementations fail the suite; "
          f"the reference passes {ref_total}/{ref_total}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
