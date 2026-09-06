"""Container security auditor: score a runtime spec for breakout risk and
produce a hardened spec.
"""
from __future__ import annotations

from engine.audit import DANGEROUS_CAPS, SENSITIVE_MOUNTS


class ContainerEscapeEngine:
    DANGEROUS_CAPS = DANGEROUS_CAPS

    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def audit(self, spec):
        risks = []
        caps = set(spec.get("capabilities", []))
        bad = caps & DANGEROUS_CAPS
        if bad:
            risks.append(f"dangerous_caps:{sorted(bad)}")
        if spec.get("privileged"):
            risks.append("privileged")
        for m in spec.get("mounts", []):
            src = str(m.get("src", ""))
            if src in SENSITIVE_MOUNTS or "docker.sock" in src:
                risks.append(f"sensitive_mount:{src}")
        if not spec.get("no_new_privileges", True):
            risks.append("no_new_privileges_disabled")
        if spec.get("user") in ("root", "0", "0:0") and not spec.get("privileged"):
            risks.append("running_as_root")
        if spec.get("network_mode") == "host":
            risks.append("host_network")
        if spec.get("pid_mode") == "host":
            risks.append("host_pid")
        return {
            "safe": not risks,
            "risks": risks,
            "score": round(max(0.0, 1.0 - 0.2 * len(risks)), 4),
        }

    def harden(self, spec):
        out = dict(spec)
        out["capabilities"] = sorted(set(out.get("capabilities", [])) - DANGEROUS_CAPS)
        out["privileged"] = False
        out["no_new_privileges"] = True
        if out.get("user") in (None, "", "root", "0", "0:0"):
            out["user"] = "1000:1000"
        out["mounts"] = [
            m for m in out.get("mounts", [])
            if str(m.get("src", "")) not in SENSITIVE_MOUNTS
            and "docker.sock" not in str(m.get("src", ""))
        ]
        if out.get("network_mode") == "host":
            out["network_mode"] = "bridge"
        if out.get("pid_mode") == "host":
            out["pid_mode"] = "private"
        out.setdefault("seccomp", "runtime/default")
        out.setdefault("apparmor", "docker-default")
        return out
