#!/bin/bash
# benchmark/tls-fingerprint grader -- Parse a TLS handshake record carrying a ClientHello; extract version, cipher suites, extension list, elliptic curves and EC point formats;…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
