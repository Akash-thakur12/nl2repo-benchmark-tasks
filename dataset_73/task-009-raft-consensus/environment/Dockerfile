# benchmark/raft-consensus -- Single-node Raft state machine (RequestVote/AppendEntries with log-conflict resolution, current-term commit rule, snapshot/restore) plus a… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
