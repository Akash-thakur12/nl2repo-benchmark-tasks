"""CLI: python3 -m flagsvc <scenario_dir> <output_json>"""
import json
import os
import sys

from .replay import replay

SUFFIX = ".scenario"


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: run.sh <scenario_dir> <output_json>\n")
        return 2
    scenario_dir, out_path = argv[1], argv[2]
    report = {}
    for name in sorted(os.listdir(scenario_dir)):
        if not name.endswith(SUFFIX):
            continue
        with open(os.path.join(scenario_dir, name), encoding="utf-8") as fh:
            report[name[: -len(SUFFIX)]] = replay(fh.read())
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
