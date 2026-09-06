#!/bin/bash
# Installs the reference repository and checks it against the shipped samples.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR/repo/." /app/
chmod +x /app/run.sh

/app/run.sh /app/samples /tmp/samples-check.json
python3 - <<'PY'
import json
got = json.load(open("/tmp/samples-check.json"))
want = json.load(open("/app/samples/expected.json"))
assert got == want, "sample report mismatch"
print("sample report reproduced")
PY
