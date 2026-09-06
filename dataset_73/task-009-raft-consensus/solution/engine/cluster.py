"""Deterministic in-process Raft cluster driver.

No threads, no wall clock: :meth:`RaftCluster.tick` advances every live node by one
logical time unit, then delivers all resulting messages (respecting the current
partition) until the message bus drains.
"""
from __future__ import annotations

from engine.engine import RaftEngine
from engine.state import ROLE_LEADER


class RaftCluster:
    def __init__(self, node_ids, seed=0, election_timeout=5, heartbeat_interval=1):
        self.node_ids = list(node_ids)
        self.nodes = {}
        for nid in self.node_ids:
            self.nodes[nid] = RaftEngine({
                "id": nid,
                "peers": list(self.node_ids),
                "seed": seed,
                "election_timeout": election_timeout,
                "heartbeat_interval": heartbeat_interval,
            })
        self._down = set()
        # partition groups: list of sets of ids that can talk to each other
        self._groups = [set(self.node_ids)]
        self._bus = []

    # ----------------------------------------------------------- topology
    def crash(self, nid):
        self._down.add(nid)

    def restart(self, nid):
        self._down.discard(nid)
        self.nodes[nid].reset()

    def partition(self, *groups):
        self._groups = [set(g) for g in groups]

    def heal(self):
        self._groups = [set(self.node_ids)]

    def _can_talk(self, a, b):
        for g in self._groups:
            if a in g and b in g:
                return True
        return False

    # -------------------------------------------------------------- run
    def _deliver(self, max_steps=10_000):
        steps = 0
        while self._bus and steps < max_steps:
            steps += 1
            msg = self._bus.pop(0)
            src, dst = msg["from"], msg["to"]
            if dst in self._down or not self._can_talk(src, dst):
                continue
            replies = self.nodes[dst].dispatch(msg)
            for r in replies:
                if r["to"] not in self._down and self._can_talk(r["from"], r["to"]):
                    self._bus.append(r)

    def tick(self, n=1):
        for _ in range(n):
            for nid in self.node_ids:
                if nid in self._down:
                    continue
                self._bus.extend(self.nodes[nid].tick())
            self._deliver()

    def run(self, ticks):
        self.tick(ticks)

    # ------------------------------------------------------------ queries
    def leader(self):
        leaders = [
            nid for nid in self.node_ids
            if nid not in self._down and self.nodes[nid].role == ROLE_LEADER
        ]
        if not leaders:
            return None
        # highest-term leader wins ties
        leaders.sort(key=lambda nid: self.nodes[nid].term, reverse=True)
        return leaders[0]

    def submit(self, cmd, settle_ticks=12):
        lid = self.leader()
        if lid is None:
            return False
        self.nodes[lid].client_append(cmd)
        self.tick(settle_ticks)
        return True

    def committed_log(self, nid):
        return self.nodes[nid].committed_commands()

    def log_terms(self, nid):
        return [e["term"] for e in self.nodes[nid].log]
