"""Reference model for the migration runner.

This is the authority for expected output; nothing is hardcoded. Section
numbers in comments refer to environment/docs/runner-spec.md; where that
document points at an artefact instead of stating a rule (1.3 -> checksums.json,
2 -> the `baseline` record, 4.5 and 6.4 -> the runbook), the comment names the
artefact the behaviour below is pinned by.
"""
import hashlib
import json


def normalize(body):
    """The form a body is stored in before it is digested.

    Pinned row by row by environment/samples/checksums.json:
      * CRLF and a lone CR become LF,
      * spaces and tabs are stripped from the end of every line,
      * trailing blank lines are dropped,
      * leading and interior whitespace, case and content are untouched.
    """
    if not body:
        return ""
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def checksum_of(up, down):
    """1.3: each body is normalized first, then the two normalized bodies are
    concatenated with no separator and hashed. The order matters:
    normalize-then-concatenate, as the "A  "/"B" and "A\\n"/"B" rows of
    samples/checksums.json show."""
    material = normalize(up) + normalize(down)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class Runner:
    def __init__(self, config):
        self.allow_out_of_order = config.get("allow_out_of_order", False)
        self.baseline = config.get("baseline", 0)

        self.versioned = {}          # version -> definition
        self.repeatable = {}         # name -> definition
        self.recorded = {}           # version -> checksum recorded when applied
        self.repeat_recorded = {}    # name -> checksum recorded when applied
        self.dirty = False
        self.locked = False

        self.applied_log = []
        self.errors = []

    # ------------------------------------------------------------- helpers
    @property
    def current(self):
        # 2: the baseline is the floor. Nothing above it applied means current
        # is the baseline itself, not null -- history is never rewritten.
        live = [v for v in self.recorded if v > self.baseline]
        return max(live) if live else (self.baseline or None)

    def _sorted_applied(self):
        # A baseline move never removes a row that was applied.
        return sorted(self.recorded)

    def _definition_checksum(self, definition):
        return checksum_of(definition.get("up"), definition.get("down"))

    def _error(self, index, code, version=None):
        self.errors.append({"command": index, "code": code, "version": version})

    # ---------------------------------------------------------- preflight
    def _preflight(self, index):
        # Every check reads self.baseline, which is whatever the most recent
        # `baseline` record left in force at this command.
        if self.locked:                                        # 3.1
            self._error(index, "LOCKED")
            return False
        if self.dirty:                                         # 3.2
            self._error(index, "DIRTY")
            return False

        drifted = sorted(
            version for version, recorded in self.recorded.items()
            if version > self.baseline and version in self.versioned
            and self._definition_checksum(self.versioned[version]) != recorded)
        if drifted:                                            # 3.3
            self._error(index, "DRIFT", drifted[0])
            return False

        missing = sorted(version for version in self.recorded
                         if version > self.baseline and version not in self.versioned)
        if missing:                                            # 3.4
            self._error(index, "MISSING", missing[0])
            return False

        if not self.allow_out_of_order:                        # 3.5
            top = self.current
            if top is not None:
                behind = sorted(v for v in self.versioned
                                if v not in self.recorded and v > self.baseline and v < top)
                if behind:
                    self._error(index, "OUT_OF_ORDER", behind[0])
                    return False
        return True

    # ----------------------------------------------------------- applying
    def _apply(self, version, index):
        """Returns True when the migration completed."""
        definition = self.versioned[version]
        if definition.get("fails"):                            # 5.3
            self._error(index, "FAILED", version)
            if not definition.get("transactional", True):      # 5.4
                self.dirty = True
            return False
        self.recorded[version] = self._definition_checksum(definition)
        self.applied_log.append({"version": version, "direction": "up"})
        return True

    def _rollback(self, version, index):
        definition = self.versioned.get(version)
        if definition is None or definition.get("down") is None:
            self._error(index, "IRREVERSIBLE", version)        # 5.2
            return False
        if definition.get("fails"):
            self._error(index, "FAILED", version)
            if not definition.get("transactional", True):
                self.dirty = True
            return False
        del self.recorded[version]
        self.applied_log.append({"version": version, "direction": "down"})
        return True

    def _run_repeatable(self, index):
        """6.1, 6.2: after a clean versioned phase, in ascending name order.

        6.4: a repeatable can fail like any other migration. It has no version
        (1.2), so the error carries version null; the phase stops there, so a
        repeatable later in name order does not run; its digest is not
        recorded, so it is retried on the next clean command; and 5.4 applies
        unchanged, so a non-transactional failure latches dirty.
        """
        for name in sorted(self.repeatable):
            definition = self.repeatable[name]
            digest = self._definition_checksum(definition)
            if self.repeat_recorded.get(name) == digest:
                continue
            if definition.get("fails"):
                self._error(index, "FAILED", None)
                if not definition.get("transactional", True):
                    self.dirty = True
                return False
            self.repeat_recorded[name] = digest
            self.applied_log.append({"name": name, "direction": "repeat"})
        return True

    # ----------------------------------------------------------- commands
    def _pending(self):
        return sorted(v for v in self.versioned
                      if v not in self.recorded and v > self.baseline)

    def cmd_up(self, record, index):
        pending = self._pending()                              # 4.1
        steps = record.get("steps")
        if steps is not None:
            pending = pending[:steps]
        for version in pending:
            if not self._apply(version, index):
                return
        self._run_repeatable(index)

    def cmd_down(self, record, index):
        steps = record.get("steps", 1)                         # 4.2
        live = [v for v in sorted(self.recorded, reverse=True) if v > self.baseline]
        for version in live[:steps]:
            if not self._rollback(version, index):
                return

    def cmd_to(self, record, index):
        target = record["target"]
        if target != 0 and target not in self.versioned:       # 4.4
            self._error(index, "UNKNOWN_TARGET", target)
            return
        top = self.current or self.baseline
        if target >= top:                                      # 4.3 forwards
            for version in self._pending():
                if version > target:
                    break
                if not self._apply(version, index):
                    return
            self._run_repeatable(index)
            return
        for version in [v for v in sorted(self.recorded, reverse=True)
                        if v > self.baseline and v > target]:
            if not self._rollback(version, index):
                return

    def cmd_repair(self, _record, index):
        # 4.5: reconcile the recorded checksums with the catalog as it stands.
        # Every recorded row is reconciled, including rows at or below the
        # baseline -- which only shows once the baseline moves back down.
        # A row whose definition has gone keeps its recorded checksum: repair
        # cannot invent one, and it must not drop the row, so MISSING survives.
        # The repeatable records are not touched, so a repeatable edited during
        # an incident still re-runs on the next up.
        for version in list(self.recorded):
            definition = self.versioned.get(version)
            if definition is not None:
                self.recorded[version] = self._definition_checksum(definition)
        self.dirty = False

    COMMANDS = {"up": "cmd_up", "down": "cmd_down", "to": "cmd_to",
                "repair": "cmd_repair"}

    def command(self, record, index):
        handler = self.COMMANDS.get(record["cmd"])
        if handler is None:
            raise ValueError("unknown command %r" % (record["cmd"],))
        if record["cmd"] == "repair":
            # repair still respects the lock but is the only way out of dirty,
            # so it is not gated by the preflight it exists to clear
            if self.locked:
                self._error(index, "LOCKED")
                return
            getattr(self, handler)(record, index)
            return
        if not self._preflight(index):
            return
        getattr(self, handler)(record, index)

    # -------------------------------------------------------------- report
    def report(self):
        return {
            "applied": self.applied_log,
            "errors": self.errors,
            "state": {"current": self.current,
                      "dirty": self.dirty,
                      "applied": self._sorted_applied()},
        }


def replay(records):
    config = records[0]
    runner = Runner(config)
    command_index = 0
    for record in records[1:]:
        op = record["op"]
        if op == "end":
            break
        if op == "define":
            if "version" in record:                            # 1.5 replaces
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
            # A state change like lock and undefine: not a command, so it does
            # not advance command_index, and it rewrites nothing.
            runner.baseline = record["version"]
        elif op == "command":
            command_index += 1
            runner.command(record, command_index)
        else:
            raise ValueError("unknown op %r" % (op,))
    return runner.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("session must begin with a config record")
    return replay(records)
