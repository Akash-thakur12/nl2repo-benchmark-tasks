#!/bin/bash
# benchmark/raft-consensus grader -- Single-node Raft state machine (RequestVote/AppendEntries with log-conflict resolution, current-term commit rule, snapshot/restore) plus a…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
