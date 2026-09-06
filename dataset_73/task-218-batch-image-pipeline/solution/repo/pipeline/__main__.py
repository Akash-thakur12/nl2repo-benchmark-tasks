"""CLI: python3 -m pipeline <manifest_dir> <output_json>"""
import json
import os
import sys

from .batch import replay_text

SUFFIX = ".manifest"


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: run.sh <manifest_dir> <output_json>\n")
        return 2
    manifest_dir, out_path = argv[1], argv[2]
    report = {}
    for name in sorted(os.listdir(manifest_dir)):
        if not name.endswith(SUFFIX):
            continue
        with open(os.path.join(manifest_dir, name), encoding="utf-8") as handle:
            report[name[: -len(SUFFIX)]] = replay_text(handle.read())
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
