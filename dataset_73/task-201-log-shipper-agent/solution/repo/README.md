# logshipper

Offline replay of the host log shipper. Given a directory of `.session`
captures, reproduce what the shipper would have delivered, dead-lettered,
dropped and left pending, and where its file offsets would have ended up.

    ./run.sh <session_dir> <output_json>

## Layout

    logshipper/config.py    parsed session configuration
    logshipper/buffer.py    the pending buffer: byte accounting, backpressure
    logshipper/files.py     per-file byte streams, read and acked offsets
    logshipper/shipper.py   the event handlers and flush policy
    logshipper/report.py    report assembly
    logshipper/__main__.py  directory walk and JSON output

The behaviour is specified in `docs/shipper-spec.md`; every rule there is
implemented in `shipper.py` with the section number in a comment.
