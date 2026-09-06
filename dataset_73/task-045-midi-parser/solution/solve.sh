#!/bin/bash
# benchmark/midi-parser grader -- SMF parser: MThd/MTrk chunks, PPQ + SMPTE division decode, VLQ delta times, running status, channel-voice messages (1 or 2 data bytes, deco…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
