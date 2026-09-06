#!/bin/bash
# benchmark/cron-parser grader -- Parse 5/6/7-field cron (minute hour dom month dow [year] with seconds when 6/7-field). Operators * / , - . Compute the next matching dateti…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
