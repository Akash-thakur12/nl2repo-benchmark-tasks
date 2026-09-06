# 2026-05-12 - P-22 disputes two quarantined rows

Support desk transcript, kept because it is the clearest worked example we have
of a report we had to defend line by line. Tickets DROP-118, DROP-131 and
DROP-142 all trace back to this call. Nothing here has been reformatted: the
drop and the report are copied out of the archive exactly as they were.

## The drop we were sent

Partner P-22, captured 2026-05-12T07:41:00Z. The schema they were issued, and
the body the capture agent took off the transfer:

```json
{
  "captured_at": "2026-05-12T07:41:00Z",
  "csv": "price,order_id,qty\n12.00,\"A-1\r\nnote\",7\n\nnot-a-decimal,\"A-2\nx\",zz\n9.99,A-3,3\n",
  "partner": "P-22",
  "schema": {
    "columns": [
      {"name": "order_id", "required": true, "type": "string"},
      {"max": 1000, "min": 1, "name": "qty", "required": true, "type": "int"},
      {"name": "price", "required": true, "type": "decimal"}
    ],
    "key": "order_id"
  }
}
```

Printed out, the body is seven physical lines. Their header is not in schema
order, and two of their records carry a line break inside a quoted field:

```
 1  price,order_id,qty
 2  12.00,"A-1
 3  note",7
 4
 5  not-a-decimal,"A-2
 6  x",zz
 7  9.99,A-3,3
```

## What we returned

```json
{
  "accepted": [
    {"order_id": "A-1\r\nnote", "price": "12.00", "qty": 7}
  ],
  "extra_columns": [],
  "quarantined": [
    {"column": "qty", "line": 5, "reason": "TYPE"},
    {"column": "qty", "line": 7, "reason": "RANGE"}
  ],
  "reject_reason": null,
  "status": "ok",
  "totals": {"accepted": 1, "data_rows": 3, "quarantined": 2}
}
```

## The call

> **P-22 (ops):** Your report says line 5 and line 7. Your old triage script
> says row 4 and row 5. Which is it?
>
> **Us:** The report. Open the file you sent us in any editor and go to line 5:
> that is where the bad record starts. It runs on to line 6, but we quote the
> line you would scroll to, not the one the record happens to finish on.
>
> **P-22 (ops):** Even though the blank line and the wrapped record are in the
> way?
>
> **Us:** Yes. We count the lines in your file, not the records. Your first
> record wraps over lines 2 and 3, line 4 is blank, so the next record starts
> at line 5. That is also why the totals say three data rows and not four -
> the blank line is not a row.
>
> **P-22 (ops):** Then line 5 - you say the problem is `qty`, but `price` on
> that line is `not-a-decimal`, and `price` comes first in our file.
>
> **Us:** It comes first in your header. We work through your schema, in the
> order your schema lists it, and we stop at the first column that fails, so
> `order_id` then `qty` then `price`. `qty` is `zz`, so that is where we
> stopped and that is the column we name. `price` was never reached.
>
> **P-22 (ops):** And line 7? `qty` is 3 there, and the drop file itself says
> the minimum is 1.
>
> **Us:** That number in the file is a cached copy the capture agent wrote; it
> is not what we agreed with you. Your `qty` floor has been 5 since June 2025 -
> revision R3 in the limits register - so 3 is out of range. If you want that
> raised we can open a new revision, but it will apply from the day it takes
> effect, not to drops you have already sent.

## Actions

- DROP-118: the retired triage script numbers by record, so it disagrees with
  the report on any drop containing a quoted line break. It has not been fixed.
- DROP-131: the same script walks the header left to right and so names the
  wrong column on a reordered header.
- DROP-142: the same script range-checks against the cached `min`/`max` in the
  drop instead of the register.
