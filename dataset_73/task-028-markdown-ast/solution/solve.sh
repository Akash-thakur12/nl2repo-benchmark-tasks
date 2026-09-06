#!/bin/bash
# benchmark/markdown-ast grader -- Parse markdown to AST: document, heading(N), paragraph, code_block, list(ordered|unordered, items), text, emphasis(strong|em), link(href).
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
