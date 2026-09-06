from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class RaftCluster:
    """Deterministic in-process Raft cluster driver. See instruction.md."""

    def __init__(self, node_ids, seed=0, election_timeout=5, heartbeat_interval=1):
        raise NotImplementedError(_STUB)

    def crash(self, nid):
        raise NotImplementedError(_STUB)

    def restart(self, nid):
        raise NotImplementedError(_STUB)

    def partition(self, *groups):
        raise NotImplementedError(_STUB)

    def heal(self):
        raise NotImplementedError(_STUB)

    def tick(self, n=1):
        raise NotImplementedError(_STUB)

    def run(self, ticks):
        raise NotImplementedError(_STUB)

    def leader(self):
        raise NotImplementedError(_STUB)

    def submit(self, cmd, settle_ticks=12):
        raise NotImplementedError(_STUB)

    def committed_log(self, nid):
        raise NotImplementedError(_STUB)

    def log_terms(self, nid):
        raise NotImplementedError(_STUB)
