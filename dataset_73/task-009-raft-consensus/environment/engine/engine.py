from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class RaftEngine:
    """Single-node Raft state machine. See instruction.md for the full contract."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def tick(self):
        raise NotImplementedError(_STUB)

    def start_election(self):
        raise NotImplementedError(_STUB)

    def become_candidate(self):
        raise NotImplementedError(_STUB)

    def quorum(self):
        raise NotImplementedError(_STUB)

    def become_leader(self):
        raise NotImplementedError(_STUB)

    def receive_vote(self, peer):
        raise NotImplementedError(_STUB)

    def handle_request_vote(self, msg):
        raise NotImplementedError(_STUB)

    def handle_request_vote_reply(self, reply):
        raise NotImplementedError(_STUB)

    def client_append(self, cmd):
        raise NotImplementedError(_STUB)

    def append(self, cmd):
        raise NotImplementedError(_STUB)

    def handle_append_entries(self, msg):
        raise NotImplementedError(_STUB)

    def handle_append_entries_reply(self, reply):
        raise NotImplementedError(_STUB)

    def replicate(self, acks):
        raise NotImplementedError(_STUB)

    def dispatch(self, msg):
        raise NotImplementedError(_STUB)

    def snapshot(self):
        raise NotImplementedError(_STUB)

    def restore(self, snap):
        raise NotImplementedError(_STUB)

    def is_leader(self):
        raise NotImplementedError(_STUB)

    def is_elected(self):
        raise NotImplementedError(_STUB)

    def committed_commands(self):
        raise NotImplementedError(_STUB)
