import json

import pytest
from engine.engine import RaftEngine
from engine.cluster import RaftCluster


# --------------------------------------------------------------- single node

def test_fresh_node_is_follower_at_term_zero():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    assert e.role == "FOLLOWER" and e.term == 0
    assert e.voted_for is None and e.commit_index == -1 and e.log == []


def test_stale_request_vote_is_rejected():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.term = 5
    r = e.handle_request_vote({
        "type": "RequestVote", "term": 3, "from": "n2", "candidate_id": "n2",
        "last_log_index": -1, "last_log_term": -1,
    })
    assert r["vote_granted"] is False and r["term"] == 5


def test_vote_denied_to_less_up_to_date_candidate():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.log = [{"term": 1, "cmd": "a"}, {"term": 2, "cmd": "b"}]
    r = e.handle_request_vote({
        "type": "RequestVote", "term": 3, "from": "n2", "candidate_id": "n2",
        "last_log_index": 0, "last_log_term": 1,
    })
    assert r["vote_granted"] is False


def test_vote_granted_once_per_term():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    m = {"type": "RequestVote", "term": 2, "candidate_id": "n2", "from": "n2",
         "last_log_index": -1, "last_log_term": -1}
    assert e.handle_request_vote(m)["vote_granted"] is True
    m2 = dict(m, candidate_id="n3", **{"from": "n3"})
    assert e.handle_request_vote(m2)["vote_granted"] is False


def test_append_entries_higher_term_steps_candidate_down():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.start_election()                       # -> CANDIDATE, term 1
    r = e.handle_append_entries({
        "type": "AppendEntries", "term": 5, "from": "n2", "leader_id": "n2",
        "prev_log_index": -1, "prev_log_term": -1, "entries": [], "leader_commit": -1,
    })
    assert e.role == "FOLLOWER" and e.term == 5 and r["success"] is True
    assert e.leader_id == "n2"


def test_leader_steps_down_on_higher_term_reply():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.role, e.term = "LEADER", 2
    e.handle_append_entries_reply({
        "type": "AppendEntriesReply", "term": 9, "from": "n2", "to": "n1",
        "success": False, "match_index": -1,
    })
    assert e.role == "FOLLOWER" and e.term == 9


def test_append_entries_consistency_check_fails_on_term_mismatch():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.log = [{"term": 1, "cmd": "a"}]
    r = e.handle_append_entries({
        "type": "AppendEntries", "term": 2, "from": "n2", "leader_id": "n2",
        "prev_log_index": 0, "prev_log_term": 2,      # follower has term 1 here
        "entries": [{"term": 2, "cmd": "b"}], "leader_commit": -1,
    })
    assert r["success"] is False and e.log == [{"term": 1, "cmd": "a"}]


def test_append_entries_appends_and_commits():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    r = e.handle_append_entries({
        "type": "AppendEntries", "term": 1, "from": "n2", "leader_id": "n2",
        "prev_log_index": -1, "prev_log_term": -1,
        "entries": [{"term": 1, "cmd": "x"}, {"term": 1, "cmd": "y"}],
        "leader_commit": 1,
    })
    assert r["success"] is True
    assert [x["cmd"] for x in e.log] == ["x", "y"] and e.commit_index == 1


def test_current_term_commit_rule():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.role, e.term = "LEADER", 2
    e.log = [{"term": 1, "cmd": "old"}]
    e.match_index = {"n1": 0, "n2": -1, "n3": -1}
    e.next_index = {"n1": 1, "n2": 1, "n3": 1}
    e.replicate({"n2": (True, 0)})            # public path -> re-checks the commit index
    assert e.commit_index == -1               # replicated, but from an earlier term
    e.client_append("new")                    # term 2 entry at index 1
    e.replicate({"n2": (True, 1)})            # majority now has the term-2 entry
    assert e.commit_index == 1


def test_reset_returns_to_fresh_state():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.start_election()
    e.log = [{"term": 1, "cmd": "z"}]
    e.reset()
    assert e.role == "FOLLOWER" and e.term == 0 and e.log == [] and e.voted_for is None


def test_configure_replaces_peer_set():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.configure({"peers": ["n1", "n2", "n3", "n4", "n5"]})
    assert set(e.peers) == {"n1", "n2", "n3", "n4", "n5"}
    assert e.quorum() == 3


# ---------------------------------------------------------------- snapshots

def test_snapshot_is_serializable_dict_with_keys():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.term, e.commit_index = 4, 1
    e.log = [{"term": 1, "cmd": "p"}, {"term": 4, "cmd": "q"}]
    e.voted_for = "n1"
    snap = e.snapshot()
    assert set(snap) == {"term", "voted_for", "log", "commit_index"}
    json.dumps(snap)                          # must not raise


def test_restore_round_trips_and_is_follower():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.term, e.role, e.commit_index = 4, "LEADER", 1
    e.log = [{"term": 1, "cmd": "p"}, {"term": 4, "cmd": "q"}]
    snap = e.snapshot()
    e2 = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e2.restore(snap)
    assert e2.term == 4 and e2.commit_index == 1 and e2.role == "FOLLOWER"
    assert [x["cmd"] for x in e2.log] == ["p", "q"]


# ----------------------------------------------------------- legacy helpers

def test_legacy_election_helpers():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.become_candidate()
    e.receive_vote("n2")
    assert e.become_leader() is True and e.role == "LEADER"


def test_legacy_replicate_advances_commit():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.become_candidate(); e.receive_vote("n2"); e.become_leader()
    e.append("x"); e.append("y")
    e.replicate({"n2": (True, 1), "n3": (True, 1)})
    assert e.commit_index == 1


def test_legacy_snapshot_restore_via_engine_pair():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.become_candidate(); e.receive_vote("n2"); e.become_leader()
    e.append("a")
    e2 = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e2.restore(e.snapshot())
    assert e2.term >= 1 and e2.log[-1]["cmd"] == "a"


def test_dispatch_rejects_unknown_message():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    with pytest.raises(ValueError):
        e.dispatch({"type": "Nonsense", "from": "n2", "to": "n1"})


# ------------------------------------------------------------------ cluster

def test_cluster_elects_single_leader():
    c = RaftCluster(["n1", "n2", "n3"])
    c.tick(20)
    assert c.leader() == "n1"
    leaders = [n for n in c.node_ids if c.nodes[n].role == "LEADER"]
    assert leaders == ["n1"]


def test_cluster_replicates_and_commits_identically():
    c = RaftCluster(["n1", "n2", "n3"])
    c.tick(20)
    c.submit("x"); c.submit("y"); c.submit("z")
    logs = [c.committed_log(n) for n in c.node_ids]
    assert all(l == ["x", "y", "z"] for l in logs)
    assert all(c.nodes[n].commit_index == 2 for n in c.node_ids)


def test_single_node_cluster_self_elects_and_commits():
    c = RaftCluster(["solo"])
    c.tick(10)
    assert c.leader() == "solo"
    c.submit("only")
    assert c.committed_log("solo") == ["only"]


def test_even_sized_cluster_quorum_is_three():
    c = RaftCluster(["a", "b", "c", "d"])
    c.tick(25)
    assert c.leader() == "a" and c.nodes["a"].quorum() == 3
    c.submit("k")
    assert all(c.committed_log(n) == ["k"] for n in c.node_ids)


def test_isolated_leader_is_superseded_and_steps_down_after_heal():
    c = RaftCluster(["n1", "n2", "n3"])
    c.tick(20)
    old = c.leader()
    c.submit("a")
    old_term = c.nodes[old].term
    old_commit = c.nodes[old].commit_index
    rest = [n for n in c.node_ids if n != old]
    c.partition({old}, set(rest))
    c.tick(30)
    # isolated leader cannot commit new entries and a higher-term leader emerges
    assert c.nodes[old].commit_index == old_commit
    new = next(n for n in rest if c.nodes[n].role == "LEADER")
    assert c.nodes[new].term > old_term
    # once reconnected the stale leader learns the newer term and steps down
    c.heal()
    c.tick(30)
    assert c.nodes[old].role == "FOLLOWER"
    assert c.leader() == new


def test_minority_makes_no_progress():
    c = RaftCluster(["n1", "n2", "n3", "n4", "n5"])
    c.tick(25)
    old = c.leader()
    c.submit("committed")
    minority = {old, next(n for n in c.node_ids if n != old)}
    majority = set(c.node_ids) - minority
    c.partition(minority, majority)
    for cmd in ("ghost1", "ghost2"):
        c.nodes[old].client_append(cmd)
    c.tick(25)
    assert c.nodes[old].commit_index == 0        # only "committed" is durable


def test_log_divergence_is_reconciled_after_heal():
    c = RaftCluster(["n1", "n2", "n3", "n4", "n5"])
    c.tick(25)
    old = c.leader()
    c.submit("a"); c.submit("b")
    minority = {old, next(n for n in c.node_ids if n != old)}
    majority = set(c.node_ids) - minority
    c.partition(minority, majority)
    for cmd in ("ghost1", "ghost2", "ghost3"):
        c.nodes[old].client_append(cmd)
    c.tick(20)
    new = next(n for n in majority if c.nodes[n].role == "LEADER")
    c.nodes[new].client_append("real1")
    c.nodes[new].client_append("real2")
    c.tick(20)
    c.heal()
    c.tick(50)
    logs = [c.committed_log(n) for n in c.node_ids]
    assert all(l == logs[0] for l in logs)
    assert all("ghost1" not in l for l in logs)
    assert logs[0][:2] == ["a", "b"] and "real1" in logs[0]


def test_crash_and_restart_node_catches_up():
    c = RaftCluster(["n1", "n2", "n3"])
    c.tick(20)
    c.submit("a")
    c.crash("n3")
    c.submit("b"); c.submit("c")
    c.restart("n3")
    c.tick(40)
    assert c.committed_log("n3") == ["a", "b", "c"]


def test_public_query_helpers():
    e = RaftEngine({"id": "n1", "peers": ["n1", "n2", "n3"]})
    e.become_candidate(); e.receive_vote("n2"); e.become_leader()
    assert e.is_leader() is True and e.is_elected() is True
    c = RaftCluster(["n1", "n2", "n3"])
    c.run(20)                                    # alias for tick(20)
    assert c.leader() == "n1"
    c.submit("a")
    assert c.log_terms("n1") == [c.nodes["n1"].term]
