# notes

Turns a range of commits into release notes: the next version, the sections and
their entries, the breaking changes, who contributed, and every commit that was
left out and why.

    ./run.sh <history_dir> <output_json>

The version bump is decided by what survives, not by what was read. A revert
takes its entry away, and with it whatever that entry was contributing: revert
the only breaking change and the release goes back to being a minor one.

## Layout

    notes/subject.py    conventional subjects, pull request references, footers
    notes/version.py    the bump and the arithmetic, including the 0.x rule
    notes/release.py    entries, duplicates, reverts, sections and the report
    notes/__main__.py   directory walk and JSON output

Behaviour is specified in `docs/release-notes-spec.md`; section numbers appear
in comments beside the rule each piece implements.
