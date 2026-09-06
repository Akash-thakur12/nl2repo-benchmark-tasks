#!/bin/bash
# benchmark/mp4-demuxer grader -- ISOBMFF/MP4 box demuxer: walk the box hierarchy (containers recurse), handle 8-byte / 64-bit / size-0-to-EOF headers, decode ftyp/mvhd/tkhd…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
