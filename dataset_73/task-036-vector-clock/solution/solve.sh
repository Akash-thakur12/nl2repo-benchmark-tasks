#!/bin/bash
# benchmark/vector-clock grader -- A single vector clock: tick(node), get/set, merge (componentwise max, idempotent+commutative), happens_before / descendant / is_concurrent…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
