#!/bin/sh
# Entry point contract: ./run.sh <capture_dir> <output_json>
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
export GOCACHE="${GOCACHE:-/tmp/.gocache}"
export GOFLAGS="-mod=mod"
cd "$DIR"
exec go run ./cmd/rollup "$@"
