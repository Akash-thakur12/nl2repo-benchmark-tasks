"""Preflight checks and commands (spec sections 3-6)."""
from .catalog import Catalog
from .state import State


class Runner:
    def __init__(self, config):
        self.allow_out_of_order = config.get("allow_out_of_order", False)
        self.catalog = Catalog()
        self.state = State(config.get("baseline", 0))
        self.applied_log = []
        self.errors = []

    # -------------------------------------------------------------- errors
    def _fail(self, index, code, version=None):
        self.errors.append({"command": index, "code": code, "version": version})
        return False

    # ----------------------------------------------------------- preflight
    def _drifted(self):
        """3.3: an applied migration whose file no longer hashes the same."""
        return sorted(
            version for version, recorded in self.state.recorded.items()
            if version > self.state.baseline
            and self.catalog.get(version) is not None
            and self.catalog.get(version).checksum != recorded)

    def _missing(self):
        """3.4: an applied migration whose definition has gone."""
        return sorted(version for version in self.state.recorded
                      if version > self.state.baseline
                      and self.catalog.get(version) is None)

    def _behind_current(self):
        """3.5: a defined but unapplied migration below the high-water mark."""
        top = self.state.current
        if top is None:
            return []
        return sorted(version for version in self.catalog.versions()
                      if not self.state.is_applied(version)
                      and self.state.baseline < version < top)

    def preflight(self, index):
        if self.state.locked:                                   # 3.1
            return self._fail(index, "LOCKED")
        if self.state.dirty:                                    # 3.2
            return self._fail(index, "DIRTY")
        drifted = self._drifted()
        if drifted:
            return self._fail(index, "DRIFT", drifted[0])
        missing = self._missing()
        if missing:
            return self._fail(index, "MISSING", missing[0])
        if not self.allow_out_of_order:
            behind = self._behind_current()
            if behind:
                return self._fail(index, "OUT_OF_ORDER", behind[0])
        return True

    # ------------------------------------------------------------ applying
    def _pending(self):
        return [v for v in self.catalog.versions()
                if not self.state.is_applied(v) and v > self.state.baseline]

    def _rollback_order(self):
        return sorted(self.state.above_baseline(), reverse=True)

    def _note_failure(self, migration, index, version):
        self._fail(index, "FAILED", version)
        if not migration.transactional:                         # 5.4
            self.state.dirty = True

    def apply(self, version, index):
        migration = self.catalog.get(version)
        if migration.fails:                                     # 5.3
            self._note_failure(migration, index, version)
            return False
        self.state.record(version, migration.checksum)          # 5.1
        self.applied_log.append({"version": version, "direction": "up"})
        return True

    def rollback(self, version, index):
        migration = self.catalog.get(version)
        if migration is None or not migration.reversible:       # 5.2
            return self._fail(index, "IRREVERSIBLE", version)
        if migration.fails:
            self._note_failure(migration, index, version)
            return False
        self.state.forget(version)
        self.applied_log.append({"version": version, "direction": "down"})
        return True

    def run_repeatable(self, index):
        """6.1, 6.2: only after a clean versioned phase, only when changed.

        6.4 points at the runbook for what happens when one fails. A
        repeatable has no version (1.2), so the FAILED entry carries version
        null - not the repeatable's name, which would not even fit the error
        shape. The phase stops there, so a repeatable later in name order does
        not run in that command; the failed one's digest is never recorded, so
        it is retried on the next clean command; and 5.4 is not restricted to
        versioned migrations, so a non-transactional repeatable failure latches
        dirty while a transactional one does not. Versioned migrations already
        applied in the same command stay applied (5.5).
        """
        for name in self.catalog.repeatable_names():
            migration = self.catalog.repeatable[name]
            digest = migration.checksum
            if self.state.repeat_recorded.get(name) == digest:
                continue
            if migration.fails:
                self._note_failure(migration, index, None)
                return False
            self.state.repeat_recorded[name] = digest
            self.applied_log.append({"name": name, "direction": "repeat"})
        return True

    # ------------------------------------------------------------ commands
    def cmd_up(self, record, index):
        steps = record.get("steps")                             # 4.1 absent: all
        pending = self._pending()
        if steps is not None:
            pending = pending[:steps]
        for version in pending:
            if not self.apply(version, index):
                return                                          # 5.5 earlier ones stay
        self.run_repeatable(index)

    def cmd_down(self, record, index):
        steps = record.get("steps", 1)                          # 4.2 absent: one
        for version in self._rollback_order()[:steps]:
            if not self.rollback(version, index):
                return

    def cmd_to(self, record, index):
        target = record["target"]
        if target != 0 and self.catalog.get(target) is None:    # 4.4
            return self._fail(index, "UNKNOWN_TARGET", target)
        top = self.state.current or self.state.baseline
        if target >= top:                                       # 4.3 forwards
            for version in self._pending():
                if version > target:
                    break
                if not self.apply(version, index):
                    return
            self.run_repeatable(index)
            return
        for version in self._rollback_order():                  # 4.3 backwards
            if version <= target:
                break
            if not self.rollback(version, index):
                return

    def cmd_repair(self, _record, _index):
        """4.5: reconcile the recorded checksums with the catalog as it stands
        now, and clear the latch. It applies nothing.

        What it does *not* put right, worked through in docs/runbook.md:

        * a row whose definition has gone keeps the checksum it has. Repair
          cannot invent a digest for a file that is not there, and dropping the
          row to make the complaint go away would lose the fact that the
          migration ran - so MISSING survives a repair and only a restored
          definition clears it.
        * the repeatable records are untouched, so a repeatable edited during
          an incident is not quietly blessed: it still re-runs on the next up.
        * rows at or below the baseline are reconciled too. That is invisible
          until the floor comes back down and those rows return to scope.
        """
        for version in list(self.state.recorded):
            migration = self.catalog.get(version)
            if migration is not None:
                self.state.record(version, migration.checksum)
        self.state.dirty = False

    COMMANDS = {"up": cmd_up, "down": cmd_down, "to": cmd_to, "repair": cmd_repair}

    def command(self, record, index):
        handler = self.COMMANDS.get(record["cmd"])
        if handler is None:
            raise ValueError("unknown command {0!r}".format(record["cmd"]))
        if record["cmd"] == "repair":
            # repair is the only way out of dirty, so it skips the dirty check,
            # but it still respects the lock
            if self.state.locked:
                self._fail(index, "LOCKED")
                return
            handler(self, record, index)
            return
        if not self.preflight(index):
            return
        handler(self, record, index)

    # -------------------------------------------------------------- report
    def report(self):
        return {
            "applied": self.applied_log,
            "errors": self.errors,
            "state": {"current": self.state.current,
                      "dirty": self.state.dirty,
                      "applied": self.state.applied_versions()},
        }
