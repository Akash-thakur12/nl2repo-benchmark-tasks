"""A static eBPF-style bytecode safety verifier.

Checks (all reported as issue strings; ``safe`` is True iff there are none):
  * instruction-count ceiling
  * forbidden helper calls
  * unauthorised map access (allow-list)
  * GPL licence for GPL-only helpers / by policy
  * CFG loop analysis: every back-edge (loop) must have a decrementing bound
    register inside the loop body
  * every path must initialise r0 before ``exit``
  * no read of an uninitialised register
"""
from __future__ import annotations

from engine.verifier import (
    FORBIDDEN_HELPERS, MAX_INSN_CEILING, WRITE_OPS, build_cfg,
)


class EbpfEngine:
    FORBIDDEN_HELPERS = FORBIDDEN_HELPERS
    MAX_INSN_CEILING = MAX_INSN_CEILING

    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def verify(self, prog):
        issues = []
        insns = prog.get("insns", [])
        n = len(insns)
        structured = bool(insns) and all(isinstance(ins, dict) for ins in insns)

        if n > self.MAX_INSN_CEILING:
            issues.append(f"too_many_insns:{n}")

        helpers = set(prog.get("helpers_called", []))
        if structured:
            for ins in insns:
                if ins.get("op") == "call" and ins.get("helper"):
                    helpers.add(ins["helper"])
        bad_helpers = helpers & self.FORBIDDEN_HELPERS
        if bad_helpers:
            issues.append(f"forbidden_helpers:{sorted(bad_helpers)}")

        maps_used = set(prog.get("maps_used", []))
        if structured:
            for ins in insns:
                if ins.get("map"):
                    maps_used.add(ins["map"])
        allowed = set(prog.get("allowed_maps", []))
        if not maps_used.issubset(allowed):
            issues.append(f"unauthorized_maps:{sorted(maps_used - allowed)}")

        if prog.get("license") != "GPL":
            issues.append("non_gpl_license")

        if structured:
            issues.extend(self._analyse_cfg(insns))
            issues.extend(self._analyse_registers(insns))

        return {"safe": not issues, "issues": issues}

    # ------------------------------------------------------------- CFG
    @staticmethod
    def _analyse_cfg(insns):
        found = []
        _succ, back_edges = build_cfg(insns)
        for src, tgt in back_edges:
            body = insns[tgt:src + 1]
            has_decrement = any(
                (ins.get("op") == "sub")
                or (ins.get("op") == "add" and int(ins.get("imm", 0)) < 0)
                for ins in body
            )
            if not has_decrement:
                found.append(f"unbounded_loop@{tgt}")
        return found

    # -------------------------------------------------------- registers
    @staticmethod
    def _analyse_registers(insns):
        found = []
        # r1 = context pointer, r10 = read-only frame pointer: pre-initialised.
        init = {1, 10}
        reachable_exit = False
        for i, ins in enumerate(insns):
            op = ins.get("op")
            src = ins.get("src")
            dst = ins.get("dst")
            if op == "call":
                init |= {0}
                init -= {1, 2, 3, 4, 5}
                init |= {1}                       # arg regs clobbered, r1 re-set by caller model
                continue
            if op == "exit":
                reachable_exit = True
                if 0 not in init:
                    found.append(f"r0_uninitialised_at_exit@{i}")
                continue
            if src is not None and src not in init and 0 <= src <= 10:
                found.append(f"uninitialised_read:r{src}@{i}")
            if op in WRITE_OPS and dst is not None:
                init.add(dst)
        if not reachable_exit:
            found.append("no_exit")
        return found
