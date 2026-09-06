#!/usr/bin/env python3
"""Prove that the visible samples cannot be passed by guessing.

Each entry below is a near-miss reading of docs/supervisor-spec.md, written as a
textual edit of tests/reference_supervisor.py. For every one this script checks
two things:

  (a) it reproduces environment/samples/expected.json exactly, so a candidate
      that adopted it would see a clean run against everything it can see, and
  (b) at least one held-out session in tests/sessions/ tells it apart from the
      reference, so the graded tests catch it.

A shortcut that fails (a) is a leak in the sample corpus: the samples are giving
away a crux and the mutation proves nothing. A shortcut that fails (b) is a hole
in the held-out corpus. Both are reported and both are failures.

Before any shortcut runs, the harness applies an empty edit and checks that the
result matches the reference on every capture. If that baseline is broken then
every shortcut fails for reasons that have nothing to do with the spec.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REFERENCE = ROOT / "tests" / "reference_supervisor.py"
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"

sys.path.insert(0, str(ROOT / "tests"))
import reference_supervisor  # noqa: E402


# ---------------------------------------------------------------- shortcuts
# name -> (why someone would read it this way, [(old, new), ...])
SHORTCUTS = {
    "timeout-inclusive": (
        "reads 2.1 as 'at least the timeout' rather than strictly greater",
        [('if self.now - worker.last_heartbeat > self.timeout:',
          'if self.now - worker.last_heartbeat >= self.timeout:')]),

    "restart-due-strict": (
        "dispatches a restart only once the due time has passed, not at it",
        [('and worker.due <= self.now:', 'and worker.due < self.now:')]),

    "backoff-first-only": (
        "uses one backoff delay for every restart instead of a table",
        [('return self.backoff[min(attempt, len(self.backoff) - 1)]',
          'return self.backoff[0]')]),

    "backoff-off-by-one": (
        "indexes the backoff table by restart number rather than by how many "
        "restarts came before",
        [('return self.backoff[min(attempt, len(self.backoff) - 1)]',
          'return self.backoff[min(attempt + 1, len(self.backoff) - 1)]')]),

    "backoff-wraps": (
        "wraps around the backoff table instead of repeating its last entry",
        [('return self.backoff[min(attempt, len(self.backoff) - 1)]',
          'return self.backoff[attempt % len(self.backoff)]')]),

    "limit-inclusive": (
        "fails the worker on reaching max_restarts rather than passing it",
        [('if len(recent) > self.max_restarts:',
          'if len(recent) >= self.max_restarts:')]),

    "window-strict": (
        "drops a crash that is exactly restart_window_ms old",
        [('recent = [t for t in worker.history if self.now - t <= self.window]',
          'recent = [t for t in worker.history if self.now - t < self.window]')]),

    "history-never-pruned": (
        "counts every crash the worker ever had, ignoring the window",
        [('recent = [t for t in worker.history if self.now - t <= self.window]',
          'recent = list(worker.history)')]),

    "reset-strict": (
        "resets the consecutive count only after more than reset_after_ms",
        [('if self.now - worker.started_at >= self.reset_after:',
          'if self.now - worker.started_at > self.reset_after:')]),

    "reset-from-heartbeat": (
        "measures the healthy spell from the last heartbeat instead of from "
        "when the worker started",
        [('if self.now - worker.started_at >= self.reset_after:',
          'if self.now - worker.last_heartbeat >= self.reset_after:')]),

    "reset-clears-history": (
        "treats the reset in 3.6 as forgiving the crashes as well",
        [('                worker.consecutive = 0\n',
          '                worker.consecutive = 0\n'
          '                worker.history = []\n')]),

    "restart-keeps-started-at": (
        "leaves started_at alone across a restart, so the healthy spell is "
        "measured from the very beginning",
        [('                worker.started_at = self.now\n', '')]),

    "restart-no-heartbeat": (
        "restarts the worker without crediting it a heartbeat",
        [('                worker.last_heartbeat = self.now\n', '')]),

    "crash-keeps-work": (
        "carries work in hand across a crash",
        [('        worker.busy = False                                  # 4.3\n', '')]),

    "drain-always-waits": (
        "always waits for a finished record before a drain completes",
        [('        if worker.busy:', '        if True:')]),

    "drain-always-immediate": (
        "stops a draining worker at once whether or not it holds work",
        [('        if worker.busy:', '        if False:')]),

    "finished-always-drains": (
        "records drained whenever work finishes",
        [('        if worker.state == DRAINING:                         # 5.2',
          '        if True:')]),

    "draining-not-checked": (
        "stops health-checking a worker once it is draining",
        [('            if worker.state not in (RUNNING, DRAINING):\n'
          '                continue',
          '            if worker.state != RUNNING:\n'
          '                continue')]),

    "heartbeat-revives": (
        "takes a heartbeat from a down worker as proof it is back, instead of "
        "waiting for the scheduled restart",
        [('        if worker is None or worker.state not in (RUNNING, DRAINING):\n'
          '            return                                           # 2.4\n'
          '        worker.last_heartbeat = self.now',
          '        if worker is None or worker.state in (STOPPED, FAILED):\n'
          '            return\n'
          '        if worker.state == DOWN:\n'
          '            worker.state = RUNNING\n'
          '            worker.started_at = self.now\n'
          '            worker.due = None\n'
          '        worker.last_heartbeat = self.now')]),

    "unknown-not-an-error": (
        "ignores a record naming a worker nobody configured",
        [('            self.errors.append({"code": "UNKNOWN_WORKER", "detail": name})',
          '            pass')]),

    "unknown-deduped": (
        "reports each unknown worker once instead of once per record",
        [('            self.errors.append({"code": "UNKNOWN_WORKER", "detail": name})',
          '            entry = {"code": "UNKNOWN_WORKER", "detail": name}\n'
          '            if entry not in self.errors:\n'
          '                self.errors.append(entry)')]),

    "sorted-worker-order": (
        "visits workers in name order rather than configuration order",
        [('        self.order = list(config["workers"])',
          '        self.order = sorted(config["workers"])')]),

    "restart-in-history": (
        "counts restarts rather than crashes against the crash-loop limit",
        [('                worker.due = None\n'
          '                self._event(worker, "restarted")',
          '                worker.due = None\n'
          '                worker.history.append(self.now)\n'
          '                self._event(worker, "restarted")')]),

    "stopped-still-checked": (
        "keeps health-checking a worker that has been drained",
        [('            if worker.state not in (RUNNING, DRAINING):\n'
          '                continue',
          '            if worker.state in (DOWN, FAILED):\n'
          '                continue')]),

    "failed-still-restarted": (
        "reads 3.3 as a label rather than as the end of the worker, and goes "
        "on restarting it",
        [('            worker.state = FAILED\n'
          '            worker.due = None\n'
          '            self._event(worker, "failed")\n'
          '            return\n',
          '            worker.state = FAILED\n'
          '            self._event(worker, "failed")\n'),
         ('            if worker.state == DOWN and worker.due is not None \\\n',
          '            if worker.state in (DOWN, FAILED) '
          'and worker.due is not None \\\n')]),

    "timeout-no-crashed-event": (
        "treats a heartbeat timeout as quietly going down rather than as a crash",
        [('            if self.now - worker.last_heartbeat > self.timeout:    # 2.1, 2.3\n'
          '                self._stop(worker)',
          '            if self.now - worker.last_heartbeat > self.timeout:    # 2.1, 2.3\n'
          '                worker.state = DOWN\n'
          '                worker.busy = False\n'
          '                worker.due = self.now + self._backoff_for(worker.consecutive)')]),

    "restarts-counts-crashes": (
        "reports the number of crashes under restarts",
        [('        worker.crashes += 1\n        self._event(worker, "crashed")',
          '        worker.crashes += 1\n        worker.restarts += 1\n'
          '        self._event(worker, "crashed")')]),

    "consecutive-never-rises": (
        "never advances the backoff table because the consecutive count is "
        "read as the number of crashes still outstanding",
        [('                worker.consecutive += 1\n', '')]),

    "drain-stops-a-down-worker": (
        "treats a drain of a down worker as stopping it for good",
        [('        if worker is None or worker.state != RUNNING:\n'
          '            return                                           # 5.5',
          '        if worker is None or worker.state in (STOPPED, FAILED):\n'
          '            return')]),

    "crash-on-stopped-counts": (
        "lets a crash record apply to a worker that has already stopped",
        [('    def op_crash(self, record):\n'
          '        self.now = record["t"]\n'
          '        worker = self._lookup(record["worker"])\n'
          '        if worker is None or worker.state not in (RUNNING, DRAINING):\n'
          '            return',
          '    def op_crash(self, record):\n'
          '        self.now = record["t"]\n'
          '        worker = self._lookup(record["worker"])\n'
          '        if worker is None or worker.state == FAILED:\n'
          '            return')]),
}


# ------------------------------------------------------------------ harness
def build(edits):
    """Return a module namespace with `edits` applied to the reference source."""
    source = REFERENCE.read_text(encoding="utf-8")
    for old, new in edits:
        if old not in source:
            raise AssertionError("edit does not apply: %r" % (old[:60],))
        source = source.replace(old, new, 1)
    namespace = {"__name__": "shortcut"}
    exec(compile(source, "<shortcut>", "exec"), namespace)
    return namespace


def captures(directory):
    return sorted(directory.glob("*.session"))


def run(namespace, path):
    try:
        return namespace["replay_text"](path.read_text(encoding="utf-8"))
    except Exception as exc:                      # a crash is its own answer
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def reference_report(path):
    return reference_supervisor.replay_text(path.read_text(encoding="utf-8"))


def main():
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    sample_paths = captures(SAMPLES)
    held_paths = captures(HELD_OUT)

    if not sample_paths or not held_paths:
        print("no captures found")
        return 1
    if len(held_paths) < 2 * len(sample_paths):
        print("held-out corpus is too small: %d held-out for %d samples"
              % (len(held_paths), len(sample_paths)))
        return 1

    # Baseline: an empty edit must reproduce the reference everywhere. Without
    # this a broken harness reads as thirty broken shortcuts.
    baseline = build([])
    for path in sample_paths + held_paths:
        if run(baseline, path) != reference_report(path):
            print("BASELINE BROKEN on %s - the harness is wrong, not the spec"
                  % path.name)
            return 1
    for name, report in expected.items():
        if reference_report(SAMPLES / (name + ".session")) != report:
            print("BASELINE BROKEN: expected.json disagrees with the reference "
                  "on %s" % name)
            return 1

    problems = []
    print("%d samples, %d held-out, %d shortcuts"
          % (len(sample_paths), len(held_paths), len(SHORTCUTS)))
    print()

    for name in sorted(SHORTCUTS):
        why, edits = SHORTCUTS[name]
        mutant = build(edits)

        agrees_with_samples = True
        for path in sample_paths:
            if run(mutant, path) != expected[path.stem]:
                agrees_with_samples = False
                problems.append("%s: caught by sample %s - the samples leak "
                                "this crux" % (name, path.stem))
                break

        caught_by = [path.stem for path in held_paths
                     if run(mutant, path) != reference_report(path)]
        if not caught_by:
            problems.append("%s: no held-out session tells it apart" % name)

        print("  %-28s samples %s   held-out catches %d  %s"
              % (name,
                 "pass" if agrees_with_samples else "FAIL",
                 len(caught_by),
                 ("(" + ", ".join(caught_by[:4])
                  + (", ..." if len(caught_by) > 4 else "") + ")")
                 if caught_by else "NONE"))

    print()
    if problems:
        for problem in problems:
            print("PROBLEM: " + problem)
        return 1
    print("all %d shortcuts reproduce the samples and are caught by the "
          "held-out corpus" % len(SHORTCUTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
