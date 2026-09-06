# registry

Replays a schema registry session: which registrations were accepted, what
version and id each one got, which were refused and why, and what each subject
looks like at the end.

    ./run.sh <registry_dir> <output_json>

Version numbers belong to a subject and are never reused. Schema ids belong to
the whole registry, so the same schema registered under two subjects carries the
same id in both.

## Layout

    registry/schema.py     schema identity and the promotion table
    registry/service.py    subjects, versions, levels and the operations
    registry/__main__.py   directory walk and JSON output

Behaviour is specified in `docs/registry-spec.md`; section numbers appear in
comments beside the rule each piece implements.
