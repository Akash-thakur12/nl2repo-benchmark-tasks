#!/bin/bash
# benchmark/tls-handshake grader -- RFC 8446 TLS 1.3 handshake FSM: full 1-RTT server-auth, HelloRetryRequest retry, mutual client-certificate auth, and PSK/0-RTT resumption b…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
