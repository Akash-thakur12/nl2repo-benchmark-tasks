#!/bin/bash
# benchmark/tor-relay grader -- Onion-routing relay: layered SHA-256 counter-mode stream cipher over fixed 498-byte cell payloads, single-layer make/decrypt plus multi-hop…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
