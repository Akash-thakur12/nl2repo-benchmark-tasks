"""The row loop (spec sections 3, 5)."""
from . import csvreader
from . import limits
from .header import Header, HeaderRejected, MISSING_COLUMNS
from .types import Rejected, parse


def _rejected(reason):
    return {
        "status": "rejected",
        "reject_reason": reason,
        "accepted": [],
        "quarantined": [],
        "extra_columns": [],
        "totals": {"data_rows": 0, "accepted": 0, "quarantined": 0},
    }


def validate(drop):
    schema = drop["schema"]
    columns = schema["columns"]
    key_name = schema["key"]

    # 3.3 the limits we defend are the register's, as of this capture. The
    # min/max cached in the drop are what the agent held, not what was agreed.
    bounds = limits.for_drop(drop, columns)

    records = csvreader.read(drop["csv"])
    if not records:
        return _rejected(MISSING_COLUMNS)

    try:
        header = Header(records[0][1], columns)
    except HeaderRejected as refusal:                 # 2.3, 2.5
        return _rejected(refusal.reason)

    accepted = []
    quarantined = []
    accepted_keys = set()
    data_rows = 0

    # `line` is the physical line the record starts on, not its ordinal: a
    # quoted line break makes those differ, and blank lines take a line too.
    for line, row in records[1:]:
        if csvreader.is_blank(row):                   # 1.6 skipped, line consumed
            continue
        data_rows += 1

        if len(row) != header.width:                  # 3.1 never padded
            quarantined.append({"line": line, "reason": "RAGGED", "column": None})
            continue

        parsed = {}
        failed_column = None
        failure_reason = None
        for column in columns:                        # 3.2 schema order, first wins
            try:
                parsed[column["name"]] = parse(
                    header.value(row, column), column,
                    bounds.get(column["name"], limits.NO_LIMITS))
            except Rejected as refusal:
                failed_column = column["name"]
                failure_reason = refusal.reason
                break

        if failed_column is not None:
            quarantined.append({"line": line, "reason": failure_reason,
                                "column": failed_column})
            continue

        # 3.5 duplication is only considered once every column has passed, so a
        # rejected row never reserves its key
        key_value = parsed[key_name]
        if key_value in accepted_keys:
            quarantined.append({"line": line, "reason": "DUPLICATE",
                                "column": key_name})
            continue

        accepted_keys.add(key_value)
        accepted.append(parsed)

    return {
        "status": "ok",
        "reject_reason": None,
        "accepted": accepted,
        "quarantined": quarantined,
        "extra_columns": header.extra,
        "totals": {"data_rows": data_rows,            # 5.3 must reconcile
                   "accepted": len(accepted),
                   "quarantined": len(quarantined)},
    }
