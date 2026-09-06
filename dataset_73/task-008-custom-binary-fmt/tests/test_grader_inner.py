# benchmark/custom-binary-fmt -- Binary record format: magic 'BIN1' (4B) | count (u16 LE) | [tag(u8), nlen(u16 LE), name(utf8), value(u32 LE)]*N. Encode/decode.
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

_STUB_MARKER = "Stub for NL2Repo evaluation"


def _iter_py(root: Path):
    """Recursively yield .py files under root, refusing to follow symlinks
    at any level (root itself, intermediate directories, or the file)."""
    if root.is_symlink():
        return
    for base, dirs, files in os.walk(root, followlinks=False):
        base_path = Path(base)
        dirs[:] = [d for d in dirs if not (base_path / d).is_symlink()]
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            p = base_path / f
            if p.is_symlink():
                continue
            yield p


def _looks_like_stub(engine_path: Path) -> bool:
    """True if the target still contains an unimplemented NL2Repo stub."""
    for p in _iter_py(engine_path):
        try:
            if _STUB_MARKER in p.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in _iter_py(root):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _is_untouched_environment(engine_path: Path) -> bool:
    """True if the target is a byte copy of this task's environment/engine stub."""
    env_engine = Path(__file__).resolve().parent.parent / "environment" / "engine"
    if not env_engine.is_dir():
        return False
    try:
        return _tree_digest(engine_path) == _tree_digest(env_engine)
    except OSError:
        return False


def run_grader(engine_dir):
    engine_path = Path(engine_dir).resolve()
    if not engine_path.exists():
        # Missing submission -> zero, never a fallback to a golden tree.
        return {"score": 0.0, "passed": 0, "failed": 0, "total": 0,
                "reason": f"engine directory not found: {engine_path}"}

    if _looks_like_stub(engine_path) or _is_untouched_environment(engine_path):
        return {"score": 0.0, "passed": 0, "failed": 0, "total": 0,
                "reason": "engine is an unimplemented stub / untouched environment"}

    # Determine package root so that `from engine.engine import ...` works
    if engine_path.name == "engine":
        pkg_parent = str(engine_path.parent)
    elif (engine_path / "engine").is_dir():
        pkg_parent = str(engine_path)
    else:
        pkg_parent = str(engine_path.parent)

    test_file = Path(__file__).resolve().parent / "test_outputs.py"
    if not test_file.exists():
        raise FileNotFoundError(f"Test file not found: {test_file}")

    env = os.environ.copy()
    env["ENGINE_DIR"] = str(engine_path)
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = pkg_parent + (os.pathsep + current_pythonpath if current_pythonpath else "")

    cmd = [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)

    passed = r.stdout.count(" PASSED")
    failed = r.stdout.count(" FAILED")
    errors = r.stdout.count(" ERROR")

    m_pass = re.search(r"(\d+)\s+passed", r.stdout)
    m_fail = re.search(r"(\d+)\s+failed", r.stdout)
    m_err = re.search(r"(\d+)\s+error", r.stdout)

    if m_pass:
        passed = max(passed, int(m_pass.group(1)))
    if m_fail:
        failed = max(failed, int(m_fail.group(1)))
    if m_err:
        errors = max(errors, int(m_err.group(1)))

    total = passed + failed + errors

    if total == 0:
        raise RuntimeError(
            f"Grader error: 0 tests collected or executed (pytest exit code {r.returncode}).\n"
            f"STDOUT:\n{r.stdout}\n"
            f"STDERR:\n{r.stderr}"
        )

    score = passed / total
    return {
        "score": round(score, 4),
        "passed": passed,
        "failed": failed + errors,
        "total": total,
    }
