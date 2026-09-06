#!/bin/bash
# Installs the reference repository and checks that it runs. An ambiguous
# task has no single correct report, so there is nothing to diff against:
# the check is that the tool runs over the shipped samples and writes a
# report of the documented shape.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR/repo/." /app/
chmod +x /app/run.sh

/app/run.sh /app/samples /tmp/samples-check.json
python3 - <<'CHECK'
import json
report = json.load(open("/tmp/samples-check.json"))
assert isinstance(report, dict) and report, "report is empty"
for name, entry in report.items():
    assert isinstance(entry, dict), "%s: entry is not an object" % name
print("sample report written for %d capture(s)" % len(report))
CHECK
