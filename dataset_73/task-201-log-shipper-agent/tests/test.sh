#!/bin/bash
# Runs in the shared environment image; pytest is baked into the Dockerfile.
# Reward is the fraction of behaviour tests that pass: NL2Repo requires a
# continuous reward in [0, 1] rather than a pass/fail bit.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier

python3 - "$SCRIPT_DIR" <<'PY'
import json, pathlib, re, subprocess, sys

script_dir = pathlib.Path(sys.argv[1]).resolve()
res = subprocess.run([sys.executable, "-m", "pytest", str(script_dir / "test_outputs.py"),
                      "-v", "--tb=short", "-p", "no:cacheprovider"],
                     capture_output=True, text=True)
print(res.stdout)
print(res.stderr, file=sys.stderr)

# Each test appears exactly once in the -v progress lines as
# "path::test_name STATUS". The short summary repeats failures as
# "STATUS path::test_name", which is why counting bare " FAILED" over the whole
# output double-counts and inflates the denominator.
progress = re.findall(r"::[\w\[\]-]+ (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b",
                      res.stdout)
passed = progress.count("PASSED")
failed = progress.count("FAILED") + progress.count("ERROR")

if not progress:                     # fall back to pytest's own summary line
    def summary(pattern):
        m = re.search(pattern, res.stdout)
        return int(m.group(1)) if m else 0
    passed = summary(r"(\d+) passed")
    failed = summary(r"(\d+) failed") + summary(r"(\d+) error")

errors = 0
total = passed + failed

if total == 0:
    print("ERROR: no tests were collected", file=sys.stderr)
    sys.exit(1)

score = passed / total
payload = {"reward": score, "score": score,
           "passed": passed, "failed": failed + errors, "total": total}
out = pathlib.Path("/logs/verifier")
out.mkdir(parents=True, exist_ok=True)
(out / "reward.json").write_text(json.dumps(payload) + "\n")
(out / "reward.txt").write_text("%.4f\n" % score)
print("=== REWARD %.4f (%d/%d) ===" % (score, passed, total))
PY
