# drift

Compares declared infrastructure against live state and reports what actually
differs, with a path you can act on.

    ./run.sh <state_dir> <output_json>

A difference of type stops the descent, so a field that turned from an object
into a list is one finding rather than a page of them. Ignore rules prune whole
subtrees but can never hide a resource that has gone missing or one nobody
declared.

## Layout

    drift/paths.py    rendering paths and matching ignore rules
    drift/compare.py  the recursive comparison
    drift/report.py   resource handling, ordering and counts
    drift/__main__.py directory walk and JSON output

Behaviour is specified in `docs/drift-spec.md`; section numbers appear in
comments beside the rule each piece implements.
