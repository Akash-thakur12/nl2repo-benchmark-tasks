#!/bin/bash
# benchmark/medical-dicom grader -- DICOM Part 10 parser: 128-byte preamble + DICM, explicit-VR LE and implicit-VR LE (dictionary), the 8- vs 12-byte element header split, VR…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
