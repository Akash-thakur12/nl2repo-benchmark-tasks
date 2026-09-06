#!/bin/bash
# benchmark/container-escape grader -- Container runtime spec auditor: audit(spec)->{safe,risks,score} flagging dangerous caps, privileged, sensitive bind-mounts (/ /proc /sys do…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
