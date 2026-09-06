"""Session parsing and the record loop."""
import json

from .runner import Runner


def parse(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("a session must start with a config record")
    return records[0], records[1:]


def replay(text):
    config, records = parse(text)
    runner = Runner(config)
    command_index = 0
    for record in records:
        op = record["op"]
        if op == "end":
            break
        if op == "define":
            runner.catalog.define(record)
        elif op == "undefine":
            runner.catalog.undefine(record["version"])
        elif op == "history":
            runner.state.record(record["version"], record["checksum"])
        elif op == "lock":
            runner.state.locked = record["held"]
        elif op == "baseline":
            # A state change like lock and undefine, not a command: it does not
            # advance the command index, and it rewrites no history. Every
            # later check simply reads whatever floor is in force by then.
            runner.state.baseline = record["version"]
        elif op == "command":
            command_index += 1                     # 7: 1-based command index
            runner.command(record, command_index)
        else:
            raise ValueError("unrecognised op {0!r}".format(op))
    return runner.report()
