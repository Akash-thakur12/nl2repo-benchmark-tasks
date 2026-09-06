#!/bin/bash
# benchmark/regulatory-mifid grader -- MiFID II RTS 22 transaction-report validator: validate(record)->list of error strings (empty=valid). Required fields, SIDE/CAPACITY enums,…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
