#!/bin/bash
# benchmark/pdf-parser grader -- ISO 32000-1 PDF parser: %PDF version, indirect objects parsed into Python structures via a primitive lexer (dict/array/name/literal+hex str…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
