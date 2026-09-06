#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out session catches it.

This script does not ship in the task image.
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_runner as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"


def m_text_ordering(R):
    class M(R):
        def _pending(self):
            return sorted((v for v in self.versioned
                           if v not in self.recorded and v > self.baseline),
                          key=str)
    return M


def m_no_drift_check(R):
    class M(R):
        def _preflight(self, index):
            if self.locked:
                self._error(index, "LOCKED")
                return False
            if self.dirty:
                self._error(index, "DIRTY")
                return False
            missing = sorted(v for v in self.recorded
                             if v > self.baseline and v not in self.versioned)
            if missing:
                self._error(index, "MISSING", missing[0])
                return False
            return self._order_check(index)

        def _order_check(self, index):
            if self.allow_out_of_order:
                return True
            top = self.current
            if top is None:
                return True
            behind = sorted(v for v in self.versioned
                            if v not in self.recorded and self.baseline < v < top)
            if behind:
                self._error(index, "OUT_OF_ORDER", behind[0])
                return False
            return True
    return M


def m_no_missing_check(R):
    class M(R):
        def _preflight(self, index):
            if self.locked:
                self._error(index, "LOCKED")
                return False
            if self.dirty:
                self._error(index, "DIRTY")
                return False
            drifted = sorted(
                v for v, recorded in self.recorded.items()
                if v > self.baseline and v in self.versioned
                and self._definition_checksum(self.versioned[v]) != recorded)
            if drifted:
                self._error(index, "DRIFT", drifted[0])
                return False
            if not self.allow_out_of_order:
                top = self.current
                if top is not None:
                    behind = sorted(v for v in self.versioned
                                    if v not in self.recorded and self.baseline < v < top)
                    if behind:
                        self._error(index, "OUT_OF_ORDER", behind[0])
                        return False
            return True
    return M


def m_missing_before_drift(R):
    class M(R):
        def _preflight(self, index):
            if self.locked:
                self._error(index, "LOCKED")
                return False
            if self.dirty:
                self._error(index, "DIRTY")
                return False
            missing = sorted(v for v in self.recorded
                             if v > self.baseline and v not in self.versioned)
            if missing:
                self._error(index, "MISSING", missing[0])
                return False
            drifted = sorted(
                v for v, recorded in self.recorded.items()
                if v > self.baseline and v in self.versioned
                and self._definition_checksum(self.versioned[v]) != recorded)
            if drifted:
                self._error(index, "DRIFT", drifted[0])
                return False
            if not self.allow_out_of_order:
                top = self.current
                if top is not None:
                    behind = sorted(v for v in self.versioned
                                    if v not in self.recorded and self.baseline < v < top)
                    if behind:
                        self._error(index, "OUT_OF_ORDER", behind[0])
                        return False
            return True
    return M


# Deliberately not listed as a shortcut: comparing out-of-order against
# `current` inclusively cannot differ from the reference, because `current` is
# always an applied version and so can never be one of the unapplied ones. It is
# kept here only to document why it is absent.
def m_out_of_order_inclusive(R):
    class M(R):
        def _preflight(self, index):
            saved = self.allow_out_of_order
            self.allow_out_of_order = True
            ok = super()._preflight(index)
            self.allow_out_of_order = saved
            if not ok:
                return False
            if saved:
                return True
            top = self.current
            if top is None:
                return True
            behind = sorted(v for v in self.versioned
                            if v not in self.recorded and self.baseline < v <= top)
            if behind:
                self._error(index, "OUT_OF_ORDER", behind[0])
                return False
            return True
    return M


def m_ignore_allow_out_of_order(R):
    class M(R):
        def __init__(self, config):
            super().__init__(config)
            self.allow_out_of_order = False
    return M


def m_baseline_not_exempt(R):
    class M(R):
        def _preflight(self, index):
            saved = self.baseline
            self.baseline = 0
            try:
                if self.locked:
                    self._error(index, "LOCKED")
                    return False
                if self.dirty:
                    self._error(index, "DIRTY")
                    return False
                drifted = sorted(
                    v for v, recorded in self.recorded.items()
                    if v in self.versioned
                    and self._definition_checksum(self.versioned[v]) != recorded)
                if drifted:
                    self._error(index, "DRIFT", drifted[0])
                    return False
                missing = sorted(v for v in self.recorded if v not in self.versioned)
                if missing:
                    self._error(index, "MISSING", missing[0])
                    return False
            finally:
                self.baseline = saved
            return True
    return M


def m_down_ignores_baseline(R):
    class M(R):
        def cmd_down(self, record, index):
            steps = record.get("steps", 1)
            for version in sorted(self.recorded, reverse=True)[:steps]:
                if not self._rollback(version, index):
                    return
    return M


def m_dirty_before_lock(R):
    class M(R):
        def _preflight(self, index):
            if self.dirty:
                self._error(index, "DIRTY")
                return False
            if self.locked:
                self._error(index, "LOCKED")
                return False
            saved_lock = self.locked
            self.locked = False
            try:
                return super()._preflight(index)
            finally:
                self.locked = saved_lock
    return M


def m_repair_keeps_dirty(R):
    class M(R):
        def cmd_repair(self, record, index):
            for version in list(self.recorded):
                definition = self.versioned.get(version)
                if definition is not None:
                    self.recorded[version] = self._definition_checksum(definition)
    return M


def m_repair_goes_through_preflight(R):
    class M(R):
        def command(self, record, index):
            if record["cmd"] == "repair":
                if not self._preflight(index):
                    return
                self.cmd_repair(record, index)
                return
            super().command(record, index)
    return M


def m_to_forward_exclusive(R):
    class M(R):
        def cmd_to(self, record, index):
            target = record["target"]
            if target != 0 and target not in self.versioned:
                self._error(index, "UNKNOWN_TARGET", target)
                return
            top = self.current or self.baseline
            if target >= top:
                for version in self._pending():
                    if version >= target:            # excludes the target itself
                        break
                    if not self._apply(version, index):
                        return
                self._run_repeatable(index)
                return
            super().cmd_to(record, index)
    return M


def m_to_backward_inclusive(R):
    class M(R):
        def cmd_to(self, record, index):
            target = record["target"]
            if target != 0 and target not in self.versioned:
                self._error(index, "UNKNOWN_TARGET", target)
                return
            top = self.current or self.baseline
            if target >= top:
                super().cmd_to(record, index)
                return
            for version in [v for v in sorted(self.recorded, reverse=True)
                            if v > self.baseline and v >= target]:
                if not self._rollback(version, index):
                    return
    return M


def m_to_zero_unknown(R):
    class M(R):
        def cmd_to(self, record, index):
            if record["target"] == 0:
                self._error(index, "UNKNOWN_TARGET", 0)
                return
            super().cmd_to(record, index)
    return M


def m_down_defaults_to_all(R):
    class M(R):
        def cmd_down(self, record, index):
            steps = record.get("steps")
            live = [v for v in sorted(self.recorded, reverse=True) if v > self.baseline]
            chosen = live if steps is None else live[:steps]
            for version in chosen:
                if not self._rollback(version, index):
                    return
    return M


def m_up_defaults_to_one(R):
    class M(R):
        def cmd_up(self, record, index):
            steps = record.get("steps", 1)
            for version in self._pending()[:steps]:
                if not self._apply(version, index):
                    return
            self._run_repeatable(index)
    return M


def m_transactional_failure_dirties(R):
    class M(R):
        def _apply(self, version, index):
            definition = self.versioned[version]
            if definition.get("fails"):
                self._error(index, "FAILED", version)
                self.dirty = True                    # regardless of transaction
                return False
            return super()._apply(version, index)
    return M


def m_failure_never_dirties(R):
    class M(R):
        def _apply(self, version, index):
            definition = self.versioned[version]
            if definition.get("fails"):
                self._error(index, "FAILED", version)
                return False
            return super()._apply(version, index)
    return M


def m_rollback_on_failure(R):
    class M(R):
        def cmd_up(self, record, index):
            before = dict(self.recorded)
            before_log = list(self.applied_log)
            super().cmd_up(record, index)
            if any(e["command"] == index and e["code"] == "FAILED" for e in self.errors):
                self.recorded = before                # undoes earlier successes
                self.applied_log = before_log
    return M


def m_repeatable_before_versioned(R):
    class M(R):
        def cmd_up(self, record, index):
            self._run_repeatable(index)
            pending = self._pending()
            steps = record.get("steps")
            if steps is not None:
                pending = pending[:steps]
            for version in pending:
                if not self._apply(version, index):
                    return
    return M


def m_repeatable_definition_order(R):
    class M(R):
        def _run_repeatable(self, index):
            for name in self.repeatable:             # insertion order
                definition = self.repeatable[name]
                digest = self._definition_checksum(definition)
                if self.repeat_recorded.get(name) == digest:
                    continue
                self.repeat_recorded[name] = digest
                self.applied_log.append({"name": name, "direction": "repeat"})
            return True
    return M


def m_repeatable_after_error(R):
    class M(R):
        def cmd_up(self, record, index):
            pending = self._pending()
            steps = record.get("steps")
            if steps is not None:
                pending = pending[:steps]
            for version in pending:
                if not self._apply(version, index):
                    break
            self._run_repeatable(index)              # runs even after a failure
    return M


def m_repeatable_on_down(R):
    class M(R):
        def cmd_down(self, record, index):
            super().cmd_down(record, index)
            self._run_repeatable(index)
    return M


def m_repeatable_always(R):
    class M(R):
        def _run_repeatable(self, index):
            for name in sorted(self.repeatable):     # ignores the checksum
                self.applied_log.append({"name": name, "direction": "repeat"})
            return True
    return M


def m_irreversible_dirties(R):
    class M(R):
        def _rollback(self, version, index):
            definition = self.versioned.get(version)
            if definition is None or definition.get("down") is None:
                self._error(index, "IRREVERSIBLE", version)
                self.dirty = True
                return False
            return super()._rollback(version, index)
    return M


# ---------------------------------------------------------------- checksums
def m_raw_checksum(R):
    """The literal reading of 1.3 before it started pointing at checksums.json,
    and the one samples/NOTES.md still endorses: hash the bodies exactly as
    they were captured."""
    class M(R):
        def _definition_checksum(self, definition):
            material = (definition.get("up") or "") + (definition.get("down") or "")
            return hashlib.sha256(material.encode("utf-8")).hexdigest()
    return M


def m_concat_then_normalize(R):
    """Normalising the concatenation rather than each body. Right for every row
    of checksums.json except the last two."""
    class M(R):
        def _definition_checksum(self, definition):
            material = (definition.get("up") or "") + (definition.get("down") or "")
            return hashlib.sha256(
                ref.normalize(material).encode("utf-8")).hexdigest()
    return M


# Deliberately not listed as a shortcut: over-correcting the normalisation by
# stripping all whitespace is already rejected by s03, whose bodies contain an
# interior space, so a candidate finds it with the visible feedback loop alone.
# It is kept here only to document why it is absent, and because h42 catches it
# anyway.
def m_normalize_everything(R):
    """Over-correcting: strip all whitespace, so a re-indent stops being drift."""
    class M(R):
        def _definition_checksum(self, definition):
            material = "".join((definition.get("up") or "").split())
            material += "".join((definition.get("down") or "").split())
            return hashlib.sha256(material.encode("utf-8")).hexdigest()
    return M


# ----------------------------------------------------------- moving baseline
def _floor_property(on_set):
    def getter(self):
        return self._floor

    def setter(self, value):
        on_set(self, value)
    return property(getter, setter)


def m_ignore_baseline_record(R):
    """Read `baseline` once out of config and ignore the capture record."""
    def on_set(self, value):
        if getattr(self, "_floor_fixed", False):
            return
        self._floor = value
        self._floor_fixed = True

    class M(R):
        baseline = _floor_property(on_set)
    return M


def m_baseline_move_rewrites_history(R):
    """Treat "already applied" as licence to forget: the move drops the rows it
    covers, so they vanish from state.applied."""
    def on_set(self, value):
        self._floor = value
        for version in list(getattr(self, "recorded", {}) or {}):
            if version <= value:
                del self.recorded[version]

    class M(R):
        baseline = _floor_property(on_set)
    return M


def m_current_null_at_baseline(R):
    """current falls to null when nothing above the floor is applied."""
    class M(R):
        @property
        def current(self):
            live = [v for v in self.recorded if v > self.baseline]
            return max(live) if live else None
    return M


def m_down_keeps_the_old_floor(R):
    """Adopt the new floor for the exemptions but keep the old one for down."""
    def on_set(self, value):
        self._floor = value
        if not hasattr(self, "_old_floor"):
            self._old_floor = value

    class M(R):
        baseline = _floor_property(on_set)

        def cmd_down(self, record, index):
            steps = record.get("steps", 1)
            floor = getattr(self, "_old_floor", self.baseline)
            live = [v for v in sorted(self.recorded, reverse=True) if v > floor]
            for version in live[:steps]:
                if not self._rollback(version, index):
                    return
    return M


# ------------------------------------------------------------------- repair
def m_repair_drops_orphans(R):
    """"Repair fixes everything": delete the applied rows whose definition has
    gone, so MISSING stops being reported."""
    class M(R):
        def cmd_repair(self, record, index):
            for version in list(self.recorded):
                definition = self.versioned.get(version)
                if definition is None:
                    del self.recorded[version]
                else:
                    self.recorded[version] = self._definition_checksum(definition)
            self.dirty = False
    return M


def m_repair_blesses_repeatables(R):
    """Repair re-records every repeatable's current digest, suppressing a
    re-run that has to happen."""
    class M(R):
        def cmd_repair(self, record, index):
            super().cmd_repair(record, index)
            for name, definition in self.repeatable.items():
                self.repeat_recorded[name] = self._definition_checksum(definition)
    return M


def m_repair_skips_under_the_floor(R):
    """Repair reconciles only the rows currently in scope, leaving the ones
    under the floor stale until the floor moves back down."""
    class M(R):
        def cmd_repair(self, record, index):
            for version in list(self.recorded):
                if version <= self.baseline:
                    continue
                definition = self.versioned.get(version)
                if definition is not None:
                    self.recorded[version] = self._definition_checksum(definition)
            self.dirty = False
    return M


# ------------------------------------------------- a repeatable that fails
def m_repeatable_failure_names_it(R):
    """Put the repeatable's name where the version goes."""
    class M(R):
        def _run_repeatable(self, index):
            for name in sorted(self.repeatable):
                definition = self.repeatable[name]
                digest = self._definition_checksum(definition)
                if self.repeat_recorded.get(name) == digest:
                    continue
                if definition.get("fails"):
                    self._error(index, "FAILED", name)
                    if not definition.get("transactional", True):
                        self.dirty = True
                    return False
                self.repeat_recorded[name] = digest
                self.applied_log.append({"name": name, "direction": "repeat"})
            return True
    return M


def m_repeatable_failure_continues(R):
    """A failing repeatable does not stop the ones after it in name order."""
    class M(R):
        def _run_repeatable(self, index):
            ok = True
            for name in sorted(self.repeatable):
                definition = self.repeatable[name]
                digest = self._definition_checksum(definition)
                if self.repeat_recorded.get(name) == digest:
                    continue
                if definition.get("fails"):
                    self._error(index, "FAILED", None)
                    if not definition.get("transactional", True):
                        self.dirty = True
                    ok = False
                    continue
                self.repeat_recorded[name] = digest
                self.applied_log.append({"name": name, "direction": "repeat"})
            return ok
    return M


def m_repeatable_failure_never_dirties(R):
    """5.4 read as being only about versioned migrations."""
    class M(R):
        def _run_repeatable(self, index):
            for name in sorted(self.repeatable):
                definition = self.repeatable[name]
                digest = self._definition_checksum(definition)
                if self.repeat_recorded.get(name) == digest:
                    continue
                if definition.get("fails"):
                    self._error(index, "FAILED", None)
                    return False
                self.repeat_recorded[name] = digest
                self.applied_log.append({"name": name, "direction": "repeat"})
            return True
    return M


def m_repeatable_failure_records_digest(R):
    """Record the digest anyway, so the failed repeatable never retries."""
    class M(R):
        def _run_repeatable(self, index):
            for name in sorted(self.repeatable):
                definition = self.repeatable[name]
                digest = self._definition_checksum(definition)
                if self.repeat_recorded.get(name) == digest:
                    continue
                self.repeat_recorded[name] = digest
                if definition.get("fails"):
                    self._error(index, "FAILED", None)
                    if not definition.get("transactional", True):
                        self.dirty = True
                    return False
                self.applied_log.append({"name": name, "direction": "repeat"})
            return True
    return M


SHORTCUTS = [
    ("versions ordered as text rather than as integers", m_text_ordering),
    ("checksum drift is not checked", m_no_drift_check),
    ("a deleted migration file is not checked", m_no_missing_check),
    ("missing is reported before drift", m_missing_before_drift),
    ("allow_out_of_order is ignored", m_ignore_allow_out_of_order),
    ("the baseline does not exempt drift and missing", m_baseline_not_exempt),
    ("down rolls back past the baseline", m_down_ignores_baseline),
    ("dirty is checked before the lock", m_dirty_before_lock),
    ("repair does not clear dirty", m_repair_keeps_dirty),
    ("repair is blocked by the preflight it is meant to fix", m_repair_goes_through_preflight),
    ("to stops short of its target going forwards", m_to_forward_exclusive),
    ("to rolls back the target itself going backwards", m_to_backward_inclusive),
    ("to 0 is an unknown target", m_to_zero_unknown),
    ("down defaults to every applied migration", m_down_defaults_to_all),
    ("up defaults to a single step", m_up_defaults_to_one),
    ("a transactional failure still latches dirty", m_transactional_failure_dirties),
    ("a failure never latches dirty", m_failure_never_dirties),
    ("earlier successes are undone when a later one fails", m_rollback_on_failure),
    ("repeatable migrations run before the versioned ones", m_repeatable_before_versioned),
    ("repeatable migrations run in definition order", m_repeatable_definition_order),
    ("repeatable migrations run even after a failure", m_repeatable_after_error),
    ("repeatable migrations run on down as well", m_repeatable_on_down),
    ("repeatable migrations run whether or not they changed", m_repeatable_always),
    ("an irreversible rollback latches dirty", m_irreversible_dirties),
    ("the checksum is taken over the bodies as captured", m_raw_checksum),
    ("the concatenation is normalised, not each body", m_concat_then_normalize),
    ("the baseline record is ignored", m_ignore_baseline_record),
    ("moving the baseline rewrites history", m_baseline_move_rewrites_history),
    ("current is null when nothing is above the baseline", m_current_null_at_baseline),
    ("down keeps the floor the session started with", m_down_keeps_the_old_floor),
    ("repair drops the rows whose definition has gone", m_repair_drops_orphans),
    ("repair re-records the repeatables too", m_repair_blesses_repeatables),
    ("repair skips the rows under the baseline", m_repair_skips_under_the_floor),
    ("a failing repeatable is named in the version field", m_repeatable_failure_names_it),
    ("a failing repeatable does not stop the batch", m_repeatable_failure_continues),
    ("a failing repeatable never latches dirty", m_repeatable_failure_never_dirties),
    ("a failing repeatable records its digest anyway", m_repeatable_failure_records_digest),
]


def run(cls, text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    runner = cls(records[0])
    index = 0
    for record in records[1:]:
        op = record["op"]
        if op == "end":
            break
        if op == "define":
            if "version" in record:
                runner.versioned[record["version"]] = record
            else:
                runner.repeatable[record["name"]] = record
        elif op == "undefine":
            runner.versioned.pop(record["version"], None)
        elif op == "history":
            runner.recorded[record["version"]] = record["checksum"]
        elif op == "lock":
            runner.locked = record["held"]
        elif op == "baseline":
            runner.baseline = record["version"]
        elif op == "command":
            index += 1
            runner.command(record, index)
    return runner.report()


def main():
    sample_files = sorted(SAMPLES.glob("*.session"))
    held_files = sorted(HELD_OUT.glob("*.session"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.replay_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.replay_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, make in SHORTCUTS:
        cls = make(ref.Runner)
        ok = True
        for f in sample_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out session:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
