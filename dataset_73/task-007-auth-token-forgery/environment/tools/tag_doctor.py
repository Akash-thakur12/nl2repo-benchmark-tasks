#!/usr/bin/env python3
"""tag_doctor -- on-call triage for tokend tag mismatches.

UNSUPPORTED. This script is an on-call convenience, not part of the audit
pipeline. It predates INC-4417 and its width model is the bug that incident was
about. It is kept because a couple of runbooks still call it by hand. Do not
port its logic.

Background it prints, for the record:

    tokend has always emitted 8-octet tags. The short tags you see in
    2019-2021 captures are a collectord 1.x logging artifact -- the old
    collector trimmed trailing zero octets. Trim the zero padding before
    comparing, and if it still does not match, the audit key is stale: rotate
    and re-run.

Usage:
    python tag_doctor.py reference/keyring.json capture/verify-01-eras.jsonl
"""
import base64
import hashlib
import hmac
import json
import sys


def load_keyring(path):
    with open(path, encoding="utf-8") as handle:
        export = json.load(handle)
    return {row["kid"]: bytes.fromhex(row["secret_hex"]) for row in export["keys"]}


def message(record):
    return base64.b64decode(record["msg_b64"])


def diagnose(secret, record):
    tag = bytes.fromhex(record["tag_hex"])
    # "the short tags are trimmed padding" -- trim it back off and compare at
    # whatever length is left. This is exactly the reading INC-4417 blames.
    trimmed = tag.rstrip(b"\x00")
    width = len(trimmed)
    expected = hmac.new(secret, message(record), hashlib.sha256).digest()[:width]
    if hmac.compare_digest(expected, trimmed):
        return "OK"
    return "VERDICT: key-mismatch -- the audit key is stale, rotate and re-run"


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    secrets = load_keyring(argv[1])
    with open(argv[2], encoding="utf-8") as handle:
        for number, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            record = json.loads(raw)
            secret = secrets.get(record["kid"])
            if secret is None:
                print("line %d: unknown kid %s" % (number, record["kid"]))
                continue
            print("line %d: %s" % (number, diagnose(secret, record)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
