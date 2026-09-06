#!/bin/bash
# benchmark/side-channel-timing grader -- Constant-time compare (hmac.compare_digest wrapper, mixed str/bytes never equal) + is_constant_time(fn) which times fn on equal vs differ-a…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
