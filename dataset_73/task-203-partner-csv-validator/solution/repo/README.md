# dropcheck

Validates partner CSV drops against the schema each partner was issued, and
reports what was accepted, what was quarantined and why.

    ./run.sh <drop_dir> <output_json>

## Layout

    dropcheck/csvreader.py   RFC 4180 reader: quoting, CRLF, byte-order mark
    dropcheck/types.py       per-type parsing and range checks
    dropcheck/limits.py      the partner limits register, resolved as of capture
    dropcheck/header.py      header validation and name-to-position mapping
    dropcheck/validator.py   row loop, quarantine reasons, duplicate detection
    dropcheck/__main__.py    directory walk and JSON output

Behaviour is specified in `docs/validation-spec.md`; section numbers appear in
comments beside the rule each piece implements.
