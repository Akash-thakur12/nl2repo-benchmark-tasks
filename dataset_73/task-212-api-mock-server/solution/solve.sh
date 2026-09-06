#!/bin/bash
# Installs the reference repository and checks it against the shipped samples
# and the shipped recordings.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR/repo/." /app/
chmod +x /app/run.sh

/app/run.sh /app/samples /tmp/samples-check.json
/app/run.sh /app/reference /tmp/reference-check.json
python3 - <<'PY'
import json
for got_path, want_path, label in (
        ("/tmp/samples-check.json", "/app/samples/expected.json", "sample"),
        ("/tmp/reference-check.json", "/app/reference/recorded.json", "recorded")):
    got = json.load(open(got_path))
    want = json.load(open(want_path))
    assert got == want, "%s report mismatch" % label
    print("%s report reproduced" % label)
PY
