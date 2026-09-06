from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class EbpfEngine:
    """Static eBPF bytecode safety verifier. See instruction.md."""

    FORBIDDEN_HELPERS = {
        "bpf_probe_write_user", "bpf_override_return", "bpf_getsockopt",
        "bpf_send_signal", "bpf_probe_read_kernel_unsafe",
    }
    MAX_INSN_CEILING = 1_000_000

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def verify(self, prog):
        raise NotImplementedError(_STUB)
