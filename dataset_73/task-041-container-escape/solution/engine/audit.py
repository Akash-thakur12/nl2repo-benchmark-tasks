from __future__ import annotations

# The single authoritative set of capabilities that enable a container breakout.
DANGEROUS_CAPS = {
    "CAP_SYS_ADMIN", "CAP_SYS_PTRACE", "CAP_SYS_MODULE", "CAP_DAC_OVERRIDE",
    "CAP_NET_ADMIN", "CAP_SETUID", "CAP_SETGID",
}

# Host paths that must never be bind-mounted into a container.
SENSITIVE_MOUNTS = {"/", "/proc", "/sys", "/var/run/docker.sock"}
