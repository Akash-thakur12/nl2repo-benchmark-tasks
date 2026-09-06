#!/usr/bin/env python3
"""quicklook - a scratch summariser for a session capture.

I wrote this on the phone during rot-4417 to get a rough shape of a capture
without waiting for the runner. It is NOT the runner: it does not model staging,
health, rollback, versions or the grace period, and it makes two assumptions I
never checked - that a record's own `t` is the time to print, and that the
environments roll out in name order. Use the runner's log for anything that
matters.

    python3 quicklook.py <session file>
"""
import json
import sys


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: quicklook.py <session file>\n")
        return 2
    records = [json.loads(line) for line in open(argv[1], encoding="utf-8")
               if line.strip()]
    config = records[0]
    envs = sorted(config["environments"])
    print("rollout order : %s" % ", ".join(envs))
    print("grace_seconds : %s" % config["grace_seconds"])
    where = {}
    for record in records[1:]:
        op = record["op"]
        if op == "consumer":
            where[record["id"]] = record["env"]
        elif op == "rotate":
            print("%s rotate%s" % (record["t"],
                                   " (dry run)" if record.get("dry_run") else ""))
        elif op == "ack":
            print("%s ack %s in %s -> v%s" % (record["t"], record["consumer"],
                                              where.get(record["consumer"], "?"),
                                              record["version"]))
        elif op == "policy":
            print("%s grace_seconds is now %s" % (record["t"],
                                                  record["grace_seconds"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
