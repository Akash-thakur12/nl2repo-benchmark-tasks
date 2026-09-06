# Container Escape Risk Auditor

## 1. Overview

Score a container runtime spec for breakout risk and produce a hardened spec.
Standard library only; code in `engine/`. `engine/audit.py` holds the single
authoritative `DANGEROUS_CAPS` set and `SENSITIVE_MOUNTS`
(`/`, `/proc`, `/sys`, `/var/run/docker.sock`).

## 2. Public API — `engine/engine.py`

### `class ContainerEscapeEngine`

- `__init__(self, config=None)` / `reset(self)` / `configure(self, options)` —
  stateless; no-ops.
- `audit(self, spec: dict) -> dict` — returns
  `{"safe": bool, "risks": [str, ...], "score": float}` where
  `score = max(0.0, 1.0 - 0.2 * len(risks))` and `safe == (risks == [])`.
  A risk string is added for each of:
  - `spec["capabilities"]` intersecting `DANGEROUS_CAPS` -> `"dangerous_caps:..."`
  - `spec["privileged"]` truthy -> `"privileged"`
  - any `spec["mounts"]` entry whose `src` is in `SENSITIVE_MOUNTS` or contains
    `"docker.sock"` -> `"sensitive_mount:<src>"`
  - `spec["no_new_privileges"]` present and false -> `"no_new_privileges_disabled"`
  - `spec["user"]` in `{"root", "0", "0:0"}` **and not** privileged ->
    `"running_as_root"`
  - `spec["network_mode"] == "host"` -> `"host_network"`
  - `spec["pid_mode"] == "host"` -> `"host_pid"`
- `harden(self, spec: dict) -> dict` — a sanitised copy: dangerous caps removed
  (others kept, sorted), `privileged=False`, `no_new_privileges=True`, a root /
  unset user replaced with `"1000:1000"`, sensitive mounts dropped, host
  network/pid switched to `bridge`/`private`, and — when absent — `seccomp` set
  to exactly `"runtime/default"` and `apparmor` to `"docker-default"`.
  `harden` is idempotent and its output passes
  `audit` as `safe`.

## 3. Example

```python
a = ContainerEscapeEngine()
a.audit({"capabilities": ["CAP_SYS_ADMIN"], "privileged": True})
# -> {"safe": False, "risks": ["dangerous_caps:['CAP_SYS_ADMIN']", "privileged"], "score": 0.6}
a.audit(a.harden(spec))["safe"]     # -> True
```

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
