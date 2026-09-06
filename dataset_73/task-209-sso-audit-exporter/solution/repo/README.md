# auditexport

Turns raw SSO sign-in events into an audit export: what was accepted, what was a
repeat of the same session, and which sign-ins could not physically have
followed the one before them.

    ./run.sh <capture_dir> <output_json>

Distances and speeds are whole-number arithmetic throughout. The distance is an
integer square root and the speed test is a cross-multiplication, so nothing is
ever divided and a zero-second gap needs no special case.

## Layout

    auditexport/geometry.py  integer distance and the speed test
    auditexport/sessions.py  the duplicate window
    auditexport/export.py    ordering, admission and travel checks
    auditexport/__main__.py  directory walk and JSON output

Behaviour is specified in `docs/audit-spec.md`; section numbers appear in
comments beside the rule each piece implements.
