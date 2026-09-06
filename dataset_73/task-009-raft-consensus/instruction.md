# Raft Consensus — Node State Machine + Deterministic Cluster Driver

## 1. Overview

Implement the core Raft protocol as two cooperating pieces, standard library only:

- `engine/engine.py` — `RaftEngine`, a **single-node** state machine. It is
  clock-free: logical time is advanced by `tick()`. All RPCs are plain dicts.
- `engine/cluster.py` — `RaftCluster`, a deterministic in-process driver that owns
  N `RaftEngine`s, advances them, and shuttles messages between them (honouring
  partitions and crashes). No threads, no wall clock.

`engine/state.py` provides the string constants
(`ROLE_FOLLOWER/CANDIDATE/LEADER`, `MSG_REQUEST_VOTE`, `MSG_REQUEST_VOTE_REPLY`,
`MSG_APPEND_ENTRIES`, `MSG_APPEND_ENTRIES_REPLY`).

## 2. Log & message shapes

- A log entry is `{"term": int, "cmd": <any>}`. `log` is a 0-indexed list;
  "log index `i`" means `log[i]`. `last_log_index` is `len(log) - 1` (`-1` when
  empty). `commit_index` starts at `-1`.
- `RequestVote`: `{"type", "term", "from", "to", "candidate_id",
  "last_log_index", "last_log_term"}`
- `RequestVoteReply`: `{"type", "term", "from", "to", "vote_granted"}`
- `AppendEntries`: `{"type", "term", "from", "to", "leader_id",
  "prev_log_index", "prev_log_term", "entries": [entry, ...], "leader_commit"}`
- `AppendEntriesReply`: `{"type", "term", "from", "to", "success", "match_index"}`

## 3. `class RaftEngine` — `engine/engine.py`

### Construction / lifecycle
- `__init__(self, config=None)` — `config` keys: `id` (str, default `"n1"`),
  `peers` (list of ids incl. self, default `["n1","n2","n3"]`), `seed` (int,
  default 0), `election_timeout` (int base, default 5), `heartbeat_interval`
  (int, default 1).
- `reset(self)` — fresh follower: `term=0`, `role="FOLLOWER"`, `voted_for=None`,
  `leader_id=None`, `log=[]`, `commit_index=-1`, `last_applied=-1`, empty
  `next_index`/`match_index`, timers zeroed.
- `configure(self, options)` — apply `peers`/`seed`/`election_timeout`/
  `heartbeat_interval` from `options`, then `reset()`.

### Public attributes (read by tests)
`id`, `peers`, `term`, `role`, `voted_for`, `leader_id`, `log`, `commit_index`,
`next_index`, `match_index`.

### Timing
- `tick(self) -> list[msg]` — advance one unit.
  - Leader: every `heartbeat_interval` ticks, return one `AppendEntries` per peer.
  - Follower / candidate: after `election_timeout` returns
    `base + rank + (seed % 3)` ticks (where `rank` is the node's position in
    `sorted(peers)`), call `start_election()` and return its messages.
  So the lowest id in a group times out first — elections are deterministic.

### Elections
- `start_election(self) -> list[msg]` — `term += 1`, `role="CANDIDATE"`,
  `voted_for=id`, votes = `{id}`, reset election timer; return one `RequestVote`
  per other peer. If `{id}` already meets quorum (single-node cluster) become
  leader immediately.
- `become_candidate(self)` — alias for `start_election`.
- `receive_vote(self, peer)` — record a granted vote from `peer`.
- `become_leader(self) -> bool` — if candidate with `>= quorum` votes: become
  leader, set `leader_id=id`, `next_index[p]=len(log)` and `match_index[p]=-1`
  for every peer, `match_index[id]=last_log_index`; return `True`. Else `False`.
  Quorum is `len(peers)//2 + 1`.
- `handle_request_vote(self, msg) -> RequestVoteReply` — step down if
  `msg.term > term`; grant iff `msg.term >= term`, `voted_for in (None,
  candidate_id)`, and the candidate log is at least as up-to-date
  (`last_log_term` greater, or equal with `last_log_index >=` ours). Granting
  sets `voted_for` and resets the election timer.
- `handle_request_vote_reply(self, reply)` — step down if `reply.term > term`;
  otherwise if still a candidate in the same term and `vote_granted`, add the
  vote and `become_leader()` once quorum is reached.

### Replication
- `client_append(self, cmd) -> bool` — leader only: append `{"term": term,
  "cmd": cmd}`, update own `match_index`/`next_index`, re-evaluate the commit
  index, return `True`. Non-leader returns `False`. `append` is an alias.
- `handle_append_entries(self, msg) -> AppendEntriesReply`
  - reject (`success=False`) if `msg.term < term`.
  - otherwise adopt `msg.term`, become follower, set `leader_id`, reset the
    election timer.
  - consistency check: if `prev_log_index >= 0` and
    (`prev_log_index >= len(log)` or `log[prev_log_index].term != prev_log_term`)
    → `success=False`.
  - else delete any conflicting suffix (first index whose term differs) and
    append the new entries; advance `commit_index` to
    `min(leader_commit, last_new_index)` when `leader_commit` is higher.
  - reply `match_index` = index of the last entry now known consistent.
- `handle_append_entries_reply(self, reply)` — step down if `reply.term > term`;
  leader only otherwise. On `success`: raise `match_index[from]` /
  `next_index[from]`, then set `commit_index` to the highest `N > commit_index`
  such that a quorum of peers has `match_index >= N` **and** `log[N].term ==
  term` (current-term rule). On failure: `next_index[from] -= 1` (floor 0).
- `replicate(self, acks)` — legacy helper: `acks` is `{peer: (ok, match_index)}`;
  feed each as an `AppendEntriesReply`.

### Persistence
- `snapshot(self) -> dict` — JSON-serializable
  `{"term", "voted_for", "log", "commit_index"}`.
- `restore(self, snap)` — load those fields; role becomes `"FOLLOWER"`,
  `leader_id` becomes `None`.

### Misc
- `dispatch(self, msg) -> list[msg]` — route one inbound message to the right
  handler; return reply messages (empty for the `*Reply` types). Unknown
  `msg["type"]` raises `ValueError`.
- `is_leader(self)` / `is_elected(self)` — `role == "LEADER"`.
- `quorum(self) -> int` — `len(peers) // 2 + 1`.
- `committed_commands(self) -> list` — `[e["cmd"] for e in log[:commit_index+1]]`.

## 4. `class RaftCluster` — `engine/cluster.py`

- `__init__(self, node_ids, seed=0, election_timeout=5, heartbeat_interval=1)` —
  build one `RaftEngine` per id (each configured with the full peer list).
  Exposes `.nodes` (id -> engine) and `.node_ids`.
- `tick(self, n=1)` — `n` times: tick every live node, collect their outbound
  messages onto a FIFO bus, then deliver the bus to completion. A message is
  dropped if its destination is crashed or the source/destination are in
  different partition groups. Replies re-enter the bus.
- `run(self, ticks)` — alias for `tick(ticks)`.
- `crash(self, nid)` / `restart(self, nid)` — remove/return a node; a restarted
  node is `reset()`.
- `partition(self, *groups)` — each `group` is an iterable of ids; only ids in
  the same group can exchange messages. `heal(self)` restores full connectivity.
- `leader(self) -> id | None` — a live node in `LEADER` role (highest term wins
  ties), else `None`.
- `submit(self, cmd, settle_ticks=12) -> bool` — append `cmd` on the current
  leader and tick `settle_ticks` to replicate; `False` if there is no leader.
- `committed_log(self, nid) -> list` — `nodes[nid].committed_commands()`.
- `log_terms(self, nid) -> list[int]` — the term of each entry in that node's log.

## 5. Guarantees the tests rely on

- A 3-node cluster elects exactly one leader (`n1`) within ~20 ticks and it is
  stable.
- After `submit(...)` calls, every node's `committed_log` is identical and
  `commit_index` matches across nodes.
- A single-node cluster elects itself and commits.
- An even-sized (4-node) cluster uses quorum 3 and still commits.
- An isolated leader keeps its role but commits nothing new; the majority elects
  a higher-term leader; after `heal()` the stale leader steps down.
- Entries appended by a partitioned minority leader that never committed are
  overwritten after the partition heals; committed entries are never lost.
- A crashed-then-restarted node catches up to the full committed log.

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
