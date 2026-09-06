#!/bin/bash
# benchmark/lsm-kv grader -- Memtable, immutable SST on flush, level-0 compaction. Get/Put/Delete. Crash-recovery via WAL.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
