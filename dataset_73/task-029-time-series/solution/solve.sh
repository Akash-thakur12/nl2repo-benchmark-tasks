#!/bin/bash
# benchmark/time-series grader -- Real bit-packed Gorilla XOR float compression: control bit 0 (repeat) / 10 (reuse prev leading/trailing window) / 11 (new 5-bit-lead + 6-bi…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
