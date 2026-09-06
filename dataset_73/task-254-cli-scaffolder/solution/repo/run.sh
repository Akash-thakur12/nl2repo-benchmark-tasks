#!/bin/sh
# Entry point contract: ./run.sh <plan_dir> <output_json>
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
exec node --experimental-strip-types --no-warnings "$DIR/src/cli.ts" "$@"
