#!/bin/bash
# benchmark/websocket-server grader -- RFC 6455 WebSocket: parse/build frames (FIN, RSV, opcode, mask, ext lengths), Sec-WebSocket-Accept handshake, close code/reason, control-fr…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
