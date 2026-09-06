"""CLI: python3 -m dropcheck <drop_dir> <output_json>"""
import json
import os
import sys

from .validator import validate

SUFFIX = ".drop"


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: run.sh <drop_dir> <output_json>\n")
        return 2
    drop_dir, out_path = argv[1], argv[2]
    report = {}
    for name in sorted(os.listdir(drop_dir)):
        if not name.endswith(SUFFIX):
            continue
        with open(os.path.join(drop_dir, name), encoding="utf-8") as handle:
            payload = json.load(handle)
        report[name[: -len(SUFFIX)]] = validate(payload)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
