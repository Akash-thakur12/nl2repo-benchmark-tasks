#!/bin/bash
# benchmark/smtp-server grader -- RFC 5321 SMTP session state machine. feed(line)->(code,text). HELO/EHLO, MAIL FROM, RCPT TO (multiple), DATA mode with dot-termination + do…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
