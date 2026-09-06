from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."

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
    """Return (successors, back_edges). See instruction.md."""
    raise NotImplementedError(_STUB)
