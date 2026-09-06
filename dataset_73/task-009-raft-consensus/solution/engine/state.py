from __future__ import annotations

ROLE_FOLLOWER = "FOLLOWER"
ROLE_CANDIDATE = "CANDIDATE"
ROLE_LEADER = "LEADER"

MSG_REQUEST_VOTE = "RequestVote"
MSG_REQUEST_VOTE_REPLY = "RequestVoteReply"
MSG_APPEND_ENTRIES = "AppendEntries"
MSG_APPEND_ENTRIES_REPLY = "AppendEntriesReply"
