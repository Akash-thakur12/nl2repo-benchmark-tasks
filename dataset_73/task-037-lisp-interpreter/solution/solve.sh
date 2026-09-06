#!/bin/bash
# benchmark/lisp-interpreter grader -- Scheme-ish interpreter: whole-program reader, lexical closures, define (+shorthand), lambda, if/cond(else), let/let*/letrec, set!, begin, a…
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
