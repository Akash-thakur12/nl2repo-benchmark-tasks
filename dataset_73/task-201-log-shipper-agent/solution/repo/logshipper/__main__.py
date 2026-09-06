"""CLI: python3 -m logshipper <session_dir> <output_json>"""
import json
import os
import sys

from .session import replay


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: run.sh <session_dir> <output_json>\n")
        return 2
    session_dir, out_path = argv[1], argv[2]
    out = {}
    for name in sorted(os.listdir(session_dir)):
        if not name.endswith(".session"):
            continue
        with open(os.path.join(session_dir, name), encoding="utf-8") as fh:
            out[name[: -len(".session")]] = replay(fh.read())
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
