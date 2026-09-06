#!/bin/bash
# benchmark/redis-lite grader -- String + List ops. SET/GET/DEL/LPUSH/RPOP/LRANGE. AOF persistence.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
