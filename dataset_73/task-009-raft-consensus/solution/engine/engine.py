"""Single-node Raft state machine.

Deterministic and clock-free: time is supplied by ``tick()`` calls. All RPCs are
plain dicts so a driver (see :mod:`engine.cluster`) can shuttle them between nodes.
"""
from __future__ import annotations

import copy

from engine.state import (
    ROLE_CANDIDATE,
    ROLE_FOLLOWER,
    ROLE_LEADER,
    MSG_APPEND_ENTRIES,
    MSG_APPEND_ENTRIES_REPLY,
    MSG_REQUEST_VOTE,
    MSG_REQUEST_VOTE_REPLY,
)


class RaftEngine:
    def __init__(self, config=None):
        cfg = config or {}
        self.id = cfg.get("id", "n1")
        self.peers = list(cfg.get("peers", ["n1", "n2", "n3"]))
        if self.id not in self.peers:
            self.peers.append(self.id)
        # Distinct, deterministic election timeouts: lowest id fires first.
        self._base_timeout = cfg.get("election_timeout", 5)
        self._heartbeat_interval = cfg.get("heartbeat_interval", 1)
        self._seed = cfg.get("seed", 0)
        self.reset()

    # ------------------------------------------------------------------ setup
    def reset(self):
        self.term = 0
        self.role = ROLE_FOLLOWER
        self.voted_for = None
        self.leader_id = None
        self.log = []                     # list of {"term": int, "cmd": any}
        self.commit_index = -1
        self.last_applied = -1
        self.next_index = {}
        self.match_index = {}
        self._votes = set()
        self._election_elapsed = 0
        self._heartbeat_elapsed = 0

    def configure(self, options):
        options = options or {}
        self.peers = list(options.get("peers", self.peers))
        if self.id not in self.peers:
            self.peers.append(self.id)
        self._base_timeout = options.get("election_timeout", self._base_timeout)
        self._heartbeat_interval = options.get(
            "heartbeat_interval", self._heartbeat_interval
        )
        self._seed = options.get("seed", self._seed)
        self.reset()

    # --------------------------------------------------------------- helpers
    def quorum(self):
        return len(self.peers) // 2 + 1

    def _election_timeout(self):
        rank = sorted(self.peers).index(self.id)
        return self._base_timeout + rank + (self._seed % 3)

    def _last_log_index(self):
        return len(self.log) - 1

    def _last_log_term(self):
        return self.log[-1]["term"] if self.log else -1

    def _step_down(self, term):
        self.term = term
        self.role = ROLE_FOLLOWER
        self.voted_for = None
        self._votes = set()

    def is_leader(self):
        return self.role == ROLE_LEADER

    def is_elected(self):
        return self.role == ROLE_LEADER

    # ------------------------------------------------------------------ time
    def tick(self):
        """Advance one logical time unit; return outbound messages."""
        if self.role == ROLE_LEADER:
            self._heartbeat_elapsed += 1
            if self._heartbeat_elapsed >= self._heartbeat_interval:
                self._heartbeat_elapsed = 0
                return self._broadcast_append_entries()
            return []
        self._election_elapsed += 1
        if self._election_elapsed >= self._election_timeout():
            return self.start_election()
        return []

    # -------------------------------------------------------------- election
    def start_election(self):
        self.term += 1
        self.role = ROLE_CANDIDATE
        self.voted_for = self.id
        self.leader_id = None
        self._votes = {self.id}
        self._election_elapsed = 0
        msgs = []
        for p in self.peers:
            if p == self.id:
                continue
            msgs.append({
                "type": MSG_REQUEST_VOTE,
                "term": self.term,
                "from": self.id,
                "to": p,
                "candidate_id": self.id,
                "last_log_index": self._last_log_index(),
                "last_log_term": self._last_log_term(),
            })
        if len(self._votes) >= self.quorum():
            self.become_leader()          # single-node cluster wins immediately
        return msgs

    # kept for backward compatibility with the classic helper name
    def become_candidate(self):
        return self.start_election()

    def receive_vote(self, peer):
        self._votes.add(peer)

    def become_leader(self):
        if self.role == ROLE_CANDIDATE and len(self._votes) >= self.quorum():
            self.role = ROLE_LEADER
            self.leader_id = self.id
            for p in self.peers:
                self.next_index[p] = len(self.log)
                self.match_index[p] = -1
            self.match_index[self.id] = self._last_log_index()
            self._heartbeat_elapsed = self._heartbeat_interval
            return True
        return False

    def handle_request_vote(self, msg):
        granted = False
        if msg["term"] > self.term:
            self._step_down(msg["term"])
        if msg["term"] >= self.term:
            up_to_date = (
                msg["last_log_term"] > self._last_log_term()
                or (
                    msg["last_log_term"] == self._last_log_term()
                    and msg["last_log_index"] >= self._last_log_index()
                )
            )
            if self.voted_for in (None, msg["candidate_id"]) and up_to_date:
                self.voted_for = msg["candidate_id"]
                self._election_elapsed = 0
                granted = True
        return {
            "type": MSG_REQUEST_VOTE_REPLY,
            "term": self.term,
            "from": self.id,
            "to": msg["from"],
            "vote_granted": granted,
        }

    def handle_request_vote_reply(self, reply):
        if reply["term"] > self.term:
            self._step_down(reply["term"])
            return
        if self.role != ROLE_CANDIDATE or reply["term"] != self.term:
            return
        if reply["vote_granted"]:
            self._votes.add(reply["from"])
            if len(self._votes) >= self.quorum():
                self.become_leader()

    # ------------------------------------------------------------ replication
    def client_append(self, cmd):
        if self.role != ROLE_LEADER:
            return False
        self.log.append({"term": self.term, "cmd": cmd})
        self.match_index[self.id] = self._last_log_index()
        self.next_index[self.id] = len(self.log)
        self._advance_commit_index()
        return True

    # legacy alias
    def append(self, cmd):
        return self.client_append(cmd)

    def _broadcast_append_entries(self):
        msgs = []
        for p in self.peers:
            if p == self.id:
                continue
            msgs.append(self._append_entries_for(p))
        return msgs

    def _append_entries_for(self, peer):
        ni = self.next_index.get(peer, len(self.log))
        prev_index = ni - 1
        prev_term = self.log[prev_index]["term"] if prev_index >= 0 else -1
        entries = [copy.deepcopy(e) for e in self.log[ni:]]
        return {
            "type": MSG_APPEND_ENTRIES,
            "term": self.term,
            "from": self.id,
            "to": peer,
            "leader_id": self.id,
            "prev_log_index": prev_index,
            "prev_log_term": prev_term,
            "entries": entries,
            "leader_commit": self.commit_index,
        }

    def handle_append_entries(self, msg):
        reply = {
            "type": MSG_APPEND_ENTRIES_REPLY,
            "term": self.term,
            "from": self.id,
            "to": msg["from"],
            "success": False,
            "match_index": -1,
        }
        if msg["term"] < self.term:
            return reply
        if msg["term"] > self.term or self.role != ROLE_FOLLOWER:
            self._step_down(msg["term"])
        self.term = msg["term"]
        self.role = ROLE_FOLLOWER
        self.leader_id = msg["leader_id"]
        self._election_elapsed = 0
        reply["term"] = self.term

        prev_i = msg["prev_log_index"]
        if prev_i >= 0:
            if prev_i >= len(self.log) or self.log[prev_i]["term"] != msg["prev_log_term"]:
                return reply  # consistency check failed

        # Append / overwrite conflicting suffix.
        insert_at = prev_i + 1
        for offset, entry in enumerate(msg["entries"]):
            idx = insert_at + offset
            if idx < len(self.log):
                if self.log[idx]["term"] != entry["term"]:
                    del self.log[idx:]
                    self.log.append(dict(entry))
            else:
                self.log.append(dict(entry))
        last_new = insert_at + len(msg["entries"]) - 1

        if msg["leader_commit"] > self.commit_index:
            self.commit_index = min(msg["leader_commit"], self._last_log_index())

        reply["success"] = True
        reply["match_index"] = last_new if msg["entries"] else prev_i
        return reply

    def handle_append_entries_reply(self, reply):
        if reply["term"] > self.term:
            self._step_down(reply["term"])
            return
        if self.role != ROLE_LEADER:
            return
        peer = reply["from"]
        if reply["success"]:
            self.match_index[peer] = max(self.match_index.get(peer, -1), reply["match_index"])
            self.next_index[peer] = self.match_index[peer] + 1
            self._advance_commit_index()
        else:
            self.next_index[peer] = max(0, self.next_index.get(peer, 1) - 1)

    def _advance_commit_index(self):
        for n in range(self._last_log_index(), self.commit_index, -1):
            if self.log[n]["term"] != self.term:
                continue
            count = sum(1 for p in self.peers if self.match_index.get(p, -1) >= n)
            if count >= self.quorum():
                self.commit_index = n
                return

    # legacy driver used by older tests: apply a dict of {peer: (ok, match_idx)}
    def replicate(self, acks):
        for peer, (ok, idx) in acks.items():
            self.handle_append_entries_reply({
                "type": MSG_APPEND_ENTRIES_REPLY,
                "term": self.term,
                "from": peer,
                "to": self.id,
                "success": ok,
                "match_index": idx,
            })

    # ---------------------------------------------------------- persistence
    def snapshot(self):
        return {
            "term": self.term,
            "voted_for": self.voted_for,
            "log": copy.deepcopy(self.log),
            "commit_index": self.commit_index,
        }

    def restore(self, snap):
        self.term = snap["term"]
        self.voted_for = snap.get("voted_for")
        self.log = [dict(e) for e in snap["log"]]
        self.commit_index = snap["commit_index"]
        self.role = ROLE_FOLLOWER
        self.leader_id = None

    # ------------------------------------------------------------- dispatch
    def dispatch(self, msg):
        """Route one inbound message; return a list of reply messages."""
        kind = msg["type"]
        if kind == MSG_REQUEST_VOTE:
            return [self.handle_request_vote(msg)]
        if kind == MSG_REQUEST_VOTE_REPLY:
            self.handle_request_vote_reply(msg)
            return []
        if kind == MSG_APPEND_ENTRIES:
            return [self.handle_append_entries(msg)]
        if kind == MSG_APPEND_ENTRIES_REPLY:
            self.handle_append_entries_reply(msg)
            return []
        raise ValueError(f"unknown message type: {kind}")

    def committed_commands(self):
        return [e["cmd"] for e in self.log[: self.commit_index + 1]]
