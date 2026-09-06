#!/bin/bash
# benchmark/quic-server grader -- QUIC (RFC 9000/9002) transport model: client-initiated bidi/uni stream-id allocation, per-stream + connection flow control (FlowControlErro…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
