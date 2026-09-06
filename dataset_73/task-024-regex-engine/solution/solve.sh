#!/bin/bash
# benchmark/regex-engine grader -- Recursive-descent regex parser -> Thompson NFA -> linear-time NFA simulation (no catastrophic backtracking). Literals, ., classes [a-z]/[^.…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
