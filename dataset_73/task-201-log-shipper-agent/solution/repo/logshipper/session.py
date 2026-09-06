"""Session parsing and the event loop."""
import json

from . import report
from .shipper import Shipper

DISPATCH = {
    "config": "config",
    "append": "append",
    "rotate": "rotate",
    "tick": "tick",
    "restart": "restart",
    "response": "response",
}


def parse(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("a session must start with a config record")
    return records[0], records[1:]


def replay(text):
    config_record, records = parse(text)
    shipper = Shipper(config_record)
    for record in records:
        op = record["op"]
        if op == "end":                       # 8.1: no final flush
            break
        method = DISPATCH.get(op)
        if method is None:
            raise ValueError("unrecognised op %r" % (op,))
        getattr(shipper, method)(record)
        shipper.enforce_spool_limit()         # 6.3: an invariant of the buffer
        shipper.flush()                       # section 4: after every event
    return report.build(shipper)
