#!/bin/bash
# benchmark/ebpf-loader grader -- Static eBPF verifier: CFG construction + back-edge loop analysis (loop must contain a decrementing bound register), per-path register init…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
