"""CLI: python3 -m notes <history_dir> <output_json>"""
import json
import os
import sys

from .release import replay_text

SUFFIX = ".history"


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: run.sh <history_dir> <output_json>\n")
        return 2
    history_dir, out_path = argv[1], argv[2]
    report = {}
    for name in sorted(os.listdir(history_dir)):
        if not name.endswith(SUFFIX):
            continue
        with open(os.path.join(history_dir, name), encoding="utf-8") as handle:
            report[name[: -len(SUFFIX)]] = replay_text(handle.read())
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
