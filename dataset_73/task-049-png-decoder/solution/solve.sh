#!/bin/bash
# benchmark/png-decoder grader -- ISO 15948 PNG decoder: 8-byte signature, chunk dissection with per-chunk CRC-32, IHDR field parse, IDAT concat + zlib inflate, undo the 5 s…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
