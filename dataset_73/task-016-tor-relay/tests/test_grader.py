# benchmark/tor-relay -- Onion-routing relay: layered SHA-256 counter-mode stream cipher over fixed 498-byte cell payloads, single-layer make/decrypt plus multi-hop…
import json
import os
import sys
from pathlib import Path


def _write_reward(res):
    for base in ("/logs/verifier", "/logs"):
        try:
            Path(base).mkdir(parents=True, exist_ok=True)
            Path(base, "reward.json").write_text(json.dumps(res) + "\n")
            Path(base, "reward.txt").write_text(f"{res['score']:.4f}\n")
            return
        except Exception:
            continue


def test_composite():
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    from test_grader_inner import run_grader

    # The grader ONLY ever evaluates the agent's own output.
    #  - explicit ENGINE_DIR wins (used by CI / oracle runs)
    #  - otherwise the in-container deploy target /app/engine
    # It NEVER falls back to solution/ (that would grade the golden answer) and it
    # NEVER silently grades the untouched environment/ stub as a pass.
    engine_dir = os.environ.get("ENGINE_DIR")
    if not engine_dir:
        engine_dir = "/app/engine"

    res = run_grader(engine_dir)
    _write_reward(res)
    assert res["score"] >= 0.5, res
