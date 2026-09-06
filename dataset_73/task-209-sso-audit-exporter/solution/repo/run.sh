#!/bin/sh
# Entry point contract: ./run.sh <capture_dir> <output_json>
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m auditexport "$@"
