#!/bin/bash
# benchmark/sql-parser grader -- Parse SELECT [DISTINCT] cols FROM t [WHERE cond] [GROUP BY] [HAVING] [ORDER BY] [LIMIT]. Produce AST.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_ENGINE:-/app/engine}"
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR/engine/." "$TARGET_DIR/"
echo "Solution deployed to $TARGET_DIR"
