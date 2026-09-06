#!/usr/bin/env python3
"""Regenerate the sample and held-out drop corpora, and samples/expected.json.

  samples/       Six drops from a partner who follows the template: header in
                 schema order, no extra columns, LF endings, no byte-order mark,
                 no quoting, every field populated and well inside the limits in
                 force for that capture, no duplicate keys and no ragged rows.
                 Almost every plausible reading of the specification reproduces
                 expected.json here - the exception is a validator that resolves
                 the range limits from the newest revision in
                 docs/partner-limits.md instead of the one in force when the
                 drop was captured, which quarantines s04's qty=900.

  tests/drops/   Held-out drops that exercise the rest of the document: RFC 4180
                 quoting (including records that span physical lines), CRLF, a
                 byte-order mark, blank lines, reordered and extra and missing
                 and duplicated headers, ragged rows, strict type parsing,
                 inclusive ranges resolved as of the capture instant, decimal
                 precision, calendar dates, and duplicate keys.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_validator  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "drops"

# The cached min/max the capture agent wrote into the drop. Deliberately the
# stale P-14 R1 pair: the authority is docs/partner-limits.md, resolved as of
# the drop's captured_at.
ORDERS = {
    "key": "order_id",
    "columns": [
        {"name": "order_id", "type": "string", "required": True},
        {"name": "qty", "type": "int", "required": True, "min": 1, "max": 1000},
        {"name": "price", "type": "decimal", "required": True},
    ],
}

FULL = {
    "key": "order_id",
    "columns": [
        {"name": "order_id", "type": "string", "required": True},
        {"name": "qty", "type": "int", "required": True, "min": 1, "max": 1000},
        {"name": "price", "type": "decimal", "required": True},
        {"name": "ship_date", "type": "date", "required": False},
        {"name": "express", "type": "bool", "required": False},
    ],
}

NL = "\n"
CRLF = "\r\n"
BOM = "﻿"

# Capture instants used below, named for the revision they fall under.
R1_TIME = "2025-11-03T09:00:00Z"        # P-14, limits 1..1000
R2_TIME = "2026-05-02T08:15:00Z"        # P-14, limits 1..500
R2_EDGE = "2026-04-01T00:00:00Z"        # P-14, the instant R2 comes into force
P22_TIME = "2025-09-14T11:30:00Z"       # P-22, limits 5..250


def rows(*lines):
    """Join record texts with LF and terminate the body, as a tidy partner would."""
    return NL.join(lines) + NL


def drop(schema, csv, partner="P-14", captured_at=R1_TIME):
    return {"partner": partner, "captured_at": captured_at,
            "schema": schema, "csv": csv}


# ------------------------------------------------------------ benign samples
def benign():
    # Decimals here are already canonical, so a validator that parses them as
    # floats still round-trips the samples. The held-out corpus is where "10.50"
    # and "0100.100" prove the original text has to be preserved.
    #
    # s04 is a P-14 capture from November 2025, so R1's max of 1000 is in force
    # and qty=900 is accepted. Reading the register's newest row instead
    # quarantines it, which is the one wrong reading the visible samples catch.
    # s02 is a P-14 capture from May 2026, under R2's max of 500, and s05 is a
    # P-22 capture under that partner's own 5..250 - both benign either way.
    return {
        "s01": drop(ORDERS, rows("order_id,qty,price", "A-1,2,10.5")),
        "s02": drop(ORDERS, rows("order_id,qty,price", "A-1,2,10.5",
                                 "A-2,5,3.0", "A-3,6,99.99"),
                    captured_at=R2_TIME),
        "s03": drop(ORDERS, rows("order_id,qty,price")),
        "s04": drop(ORDERS, rows("order_id,qty,price", "B-1,4,0.01",
                                 "B-2,900,1234.56"),
                    captured_at="2025-11-20T16:05:00Z"),
        "s05": drop(FULL, rows("order_id,qty,price,ship_date,express",
                               "C-1,30,15.0,2026-03-01,true",
                               "C-2,40,20.0,2026-03-02,false"),
                    partner="P-22", captured_at=P22_TIME),
        "s06": drop(FULL, rows("order_id,qty,price,ship_date,express",
                               "D-1,7,7.77,2024-02-29,true")),
    }


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}
    head = "order_id,qty,price"

    # -- RFC 4180 quoting (1.2, 1.3) ---------------------------------------
    s["h01"] = drop(ORDERS, rows(head, '"A,1",2,10.50'))
    s["h02"] = drop(ORDERS, rows(head, '"A""1",2,10.50'))
    # A record that spans two physical lines and fails: the quarantine line is
    # the line the record BEGINS on (2), not the one it ends on (3).
    s["h03"] = drop(ORDERS, rows(head, '"line1' + NL + 'line2",zz,10.50'))
    s["h04"] = drop(ORDERS, rows(head, 'ab"cd,2,10.50'))
    s["h05"] = drop(ORDERS, rows(head, '"",2,10.50'))

    # -- line terminators and the byte-order mark (1.1, 1.4, 1.5) ----------
    s["h06"] = drop(ORDERS, head + CRLF + "A-1,2,10.50" + CRLF)
    s["h07"] = drop(ORDERS, BOM + rows(head, "A-1,2,10.50"))
    s["h08"] = drop(ORDERS, head + NL + "A-1,2,10.50")
    # The first record swallows a CRLF, so the failing second record is record
    # ordinal 3 but physical line 4.
    s["h09"] = drop(ORDERS, rows(head, '"has' + CRLF + 'newline",2,10.50',
                                 "A-2,zz,1.00"))

    # -- blank lines are skipped but still consume a line number (1.6) -----
    s["h10"] = drop(ORDERS, rows(head, "A-1,2,10.50", "", "A-2,x,1.00"))

    # -- header order, extras, missing, duplicates (2.2 - 2.5) -------------
    s["h11"] = drop(ORDERS, rows("price,order_id,qty", "10.50,A-1,2"))
    s["h12"] = drop(ORDERS, rows("order_id,partner_ref,qty,price", "A-1,ZZ,2,10.50"))
    s["h13"] = drop(ORDERS, rows("order_id,qty", "A-1,2"))
    s["h14"] = drop(ORDERS, rows("order_id,qty,price,qty", "A-1,2,10.50,3"))
    s["h15"] = drop(ORDERS, rows("Order_ID,qty,price", "A-1,2,10.50"))

    # -- ragged rows are never padded (3.1) --------------------------------
    s["h16"] = drop(ORDERS, rows(head, "A-1,2", "A-2,3,1.00,extra", "A-3,1,2.00"))

    # -- required empty vs optional empty (3.3, 3.4) -----------------------
    s["h17"] = drop(ORDERS, rows(head, ",2,10.50"))
    s["h18"] = drop(FULL, rows("order_id,qty,price,ship_date,express", "E-1,2,10.50,,"))

    # -- strict int parsing (4.2), captured exactly at the instant R2 comes
    # -- into force, so R2's max of 500 applies to A-6 and the cached 1000 in
    # -- the drop does not.
    s["h19"] = drop(ORDERS, rows(head, "A-1,1.0,10.50", "A-2,+1,10.50",
                                 "A-3, 1,10.50", "A-4,1e2,10.50", "A-5,-3,10.50",
                                 "A-6,900,10.50"),
                    captured_at=R2_EDGE)

    # -- inclusive range bounds under R1 (3.3) -----------------------------
    s["h20"] = drop(ORDERS, rows(head, "A-1,1,10.50", "A-2,1000,10.50",
                                 "A-3,0,10.50", "A-4,1001,10.50"))

    # -- decimal keeps its original text (4.3) -----------------------------
    s["h21"] = drop(ORDERS, rows(head, "A-1,2,10.50", "A-2,2,0100.100",
                                 "A-3,2,.5", "A-4,2,5.", "A-5,2,-1.25"))

    # -- calendar dates (4.4) ----------------------------------------------
    s["h22"] = drop(FULL, rows("order_id,qty,price,ship_date,express",
                               "F-1,1,1.00,2026-1-5,true",
                               "F-2,1,1.00,2026-02-30,true",
                               "F-3,1,1.00,20260105,true",
                               "F-4,1,1.00,2026-02-29,true",
                               "F-5,1,1.00,2024-02-29,true"))

    # -- booleans are lower case only (4.5) --------------------------------
    s["h23"] = drop(FULL, rows("order_id,qty,price,ship_date,express",
                               "G-1,1,1.00,2026-03-01,TRUE",
                               "G-2,1,1.00,2026-03-01,1",
                               "G-3,1,1.00,2026-03-01,yes",
                               "G-4,1,1.00,2026-03-01,false"))

    # -- duplicate keys: first wins (3.5) ----------------------------------
    s["h24"] = drop(ORDERS, rows(head, "A-1,2,10.50", "A-1,9,1.00", "A-2,3,2.00"))

    # -- a rejected row does not reserve its key (3.2 before 3.5) ----------
    s["h25"] = drop(ORDERS, rows(head, "A-1,zz,10.50", "A-1,2,10.50"))

    # -- type failure is reported before duplication (3.2, 3.5) ------------
    s["h26"] = drop(ORDERS, rows(head, "A-1,2,10.50", "A-1,zz,10.50"))

    # -- first failing column in schema order wins (3.2) -------------------
    s["h27"] = drop(ORDERS, rows(head, "A-1,zz,not-a-decimal"))
    s["h28"] = drop(ORDERS, rows(head, ",zz,10.50"))

    # -- extra columns are ignored, not validated (2.4, 5.1), and this is a
    # -- P-22 capture, so that partner's own 5..250 applies: qty=2 is out of
    # -- range for P-22 even though it is fine for P-14.
    s["h29"] = drop(ORDERS, rows("order_id,qty,price,junk",
                                 "A-1,20,10.50,!!!", "A-2,2,1.00,???"),
                    partner="P-22", captured_at=P22_TIME)

    # -- a header-only drop with extras ------------------------------------
    s["h30"] = drop(ORDERS, rows("order_id,qty,price,extra1,extra2"))

    # -- totals must reconcile across every outcome (5.3), with a record that
    # -- spans two physical lines above a blank line, so multiline records and
    # -- blank lines shift every later quarantine line together.
    s["h31"] = drop(ORDERS, rows(head, '"Z-1' + NL + 'note",2,10.50',
                                 "A-1,2,10.50", "", "A-2,bad,1.00",
                                 "A-3,3", "A-1,4,1.00", ""))

    # -- with a reordered header, the first failure must still be the first
    # -- failing column in SCHEMA order (3.2) ------------------------------
    s["h32"] = drop(ORDERS, rows("price,order_id,qty", "not-a-decimal,A-1,zz"))

    return s


def write(target, drops):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(drops.items()):
        (target / (name + ".drop")).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".drop")).read_text(encoding="utf-8")
        expected[name] = reference_validator.validate_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
