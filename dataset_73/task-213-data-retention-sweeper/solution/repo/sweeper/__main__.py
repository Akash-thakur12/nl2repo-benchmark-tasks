"""CLI: python3 -m sweeper <sweep_dir> <output_json>"""
import json
import os
import sys

from .sweep import run_text

SUFFIX = ".sweep"


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: run.sh <sweep_dir> <output_json>\n")
        return 2
    sweep_dir, out_path = argv[1], argv[2]
    report = {}
    for name in sorted(os.listdir(sweep_dir)):
        if not name.endswith(SUFFIX):
            continue
        with open(os.path.join(sweep_dir, name), encoding="utf-8") as handle:
            report[name[: -len(SUFFIX)]] = run_text(handle.read())
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
