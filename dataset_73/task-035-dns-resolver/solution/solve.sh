#!/bin/bash
# benchmark/dns-resolver grader -- RFC 1035 DNS: encode/parse names (compression pointers, loop-safe), build a query packet, parse full response (header flags, question/answe…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
