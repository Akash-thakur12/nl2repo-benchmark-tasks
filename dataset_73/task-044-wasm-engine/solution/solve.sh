#!/bin/bash
# benchmark/wasm-engine grader -- WebAssembly MVP interpreter: operand-stack VM with structured control flow (block/loop/if/else/end + br/br_if/return resolved to jump targe…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
