#!/bin/bash
# benchmark/json-parser grader -- From-scratch RFC 8259 JSON parser (no json module): recursive descent over a hand-rolled lexer. Objects, arrays, strings (all escapes + XXX…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
