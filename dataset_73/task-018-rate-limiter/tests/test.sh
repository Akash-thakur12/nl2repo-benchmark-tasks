#!/bin/bash
# benchmark/rate-limiter grader -- Per-key bucket: capacity, refill rate. Allow/detect. Distributed-aware (Redis-like) and sliding window variants.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier 2>/dev/null || true

if [ -d "/app" ]; then
    cd /app
else
    cd "$SCRIPT_DIR/.."
fi

python3 -c "
import subprocess, sys, json, re
from pathlib import Path

script_dir = Path('$SCRIPT_DIR').resolve()
test_file = script_dir / 'test_outputs.py'

res = subprocess.run([sys.executable, '-m', 'pytest', str(test_file), '-v', '--tb=short'], capture_output=True, text=True)
print(res.stdout)
print(res.stderr, file=sys.stderr)

# Each test appears exactly once in the -v progress lines as
# 'path::test_name STATUS'. The short summary repeats failures as
# 'STATUS path::test_name', so counting the bare substring over the whole
# output double-counts failures and inflates the denominator.
progress = re.findall(r'::[\w\[\]-]+ (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b',
                      res.stdout)
passed = progress.count('PASSED')
failed = progress.count('FAILED') + progress.count('ERROR')
errors = 0

if not progress:
    def summary(pattern):
        m = re.search(pattern, res.stdout)
        return int(m.group(1)) if m else 0
    passed = summary(r'(\d+)\s+passed')
    failed = summary(r'(\d+)\s+failed') + summary(r'(\d+)\s+error')

total = passed + failed + errors

if total == 0:
    print('ERROR: 0 tests collected or executed!', file=sys.stderr)
    sys.exit(1)

score = (passed / total) if total > 0 else 0.0

result_payload = {'reward': score, 'score': score, 'passed': passed, 'failed': failed + errors, 'total': total}
reward_text = f'{score:.4f}\n'
reward_json = json.dumps(result_payload) + '\n'

# Belt-and-suspenders: write the reward to every plausible location a QC
# substrate might scrape from, not just /logs/verifier. A single-path write
# that lands somewhere the harness doesn't look produces a silent
# no-reward-metric result indistinguishable from a real infra failure.
candidate_dirs = [
    '/logs/verifier',
    '/logs',
    str(script_dir.parent / 'verifier'),
    str(script_dir.parent),
    '/app',
    '.',
]
for d in candidate_dirs:
    try:
        Path(d).mkdir(parents=True, exist_ok=True)
        Path(d, 'reward.txt').write_text(reward_text)
        Path(d, 'reward.json').write_text(reward_json)
    except Exception as e:
        print(f'Warning: failed to write reward to {d}: {e}', file=sys.stderr)

print(f'=== HARBOR REWARD: {score} ({passed}/{total}) ===')
"
