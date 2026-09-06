from __future__ import annotations

MAX_INSN_CEILING = 1_000_000

FORBIDDEN_HELPERS = {
    "bpf_probe_write_user", "bpf_override_return", "bpf_getsockopt",
    "bpf_send_signal", "bpf_probe_read_kernel_unsafe",
}

# opcodes that transfer control
JUMP_OPS = {"jmp", "ja", "jeq", "jne", "jlt", "jle", "jgt", "jge", "jset"}
COND_JUMP_OPS = JUMP_OPS - {"jmp", "ja"}

# opcodes that write their dst register
WRITE_OPS = {"mov", "add", "sub", "mul", "div", "and", "or", "xor", "lsh",
             "rsh", "ld", "ldx", "ldmapfd"}


def build_cfg(insns):
    """Return (successors, back_edges). successors[i] is a list of target indices."""
    n = len(insns)
    succ = {i: [] for i in range(n)}
    for i, ins in enumerate(insns):
        op = ins.get("op")
        if op == "exit":
            continue
        if op in JUMP_OPS:
            target = i + 1 + int(ins.get("off", 0))
            if 0 <= target < n:
                succ[i].append(target)
            if op in COND_JUMP_OPS and i + 1 < n:
                succ[i].append(i + 1)          # fall-through when not taken
        else:
            if i + 1 < n:
                succ[i].append(i + 1)
    back_edges = [(i, t) for i, ts in succ.items() for t in ts if t <= i]
    return succ, back_edges
