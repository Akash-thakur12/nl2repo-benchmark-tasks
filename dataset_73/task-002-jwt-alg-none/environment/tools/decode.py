#!/usr/bin/env python3
"""Split a compact JWT into its parts and print them.

Does no verification whatsoever -- it is a hex-dump for tokens, used when
reading `samples/gateway_corpus.jsonl` by hand.

    python tools/decode.py <token>
    python tools/decode.py --corpus <id>     # decode a corpus line's token
    python tools/decode.py --corpus-list     # list the corpus line ids

The MAC is printed with its byte length, which is the quickest way to see
which digest actually produced a signature: 32 bytes is SHA-256, 48 is
SHA-384, 64 is SHA-512.
"""
import base64
import binascii
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(os.path.dirname(HERE), "samples", "gateway_corpus.jsonl")


def b64d(segment):
    raw = segment.encode("utf-8")
    return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))


def show(token):
    parts = token.split(".")
    print("segments: %d" % len(parts))
    if len(parts) != 3:
        print("  not a three-segment token")
        return
    header, payload, signature = parts
    for label, segment in (("header", header), ("payload", payload)):
        print("%s:" % label)
        print("  raw   %s" % segment)
        try:
            print("  json  %s" % json.dumps(json.loads(b64d(segment))))
        except (ValueError, binascii.Error) as exc:
            print("  json  <undecodable: %s>" % exc)
    print("signature:")
    print("  raw   %s" % (signature or "<empty>"))
    try:
        mac = b64d(signature)
    except binascii.Error as exc:
        print("  bytes <undecodable: %s>" % exc)
        return
    print("  bytes %d" % len(mac))
    print("  hex   %s" % mac.hex())
    print("signing input: %s.%s" % (header, payload))


def corpus_rows():
    with open(CORPUS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--corpus-list":
        for row in corpus_rows():
            print("%-34s %-7s %-13s %s"
                  % (row["id"], row["op"], row["verdict"],
                     row.get("code") or ""))
        return 0
    if argv[0] == "--corpus":
        wanted = argv[1]
        for row in corpus_rows():
            if row["id"] == wanted:
                print("# %s -- %s" % (row["id"], row["note"]))
                print("# state: %s" % json.dumps(row["state"]))
                print("# verdict: %s  code: %s"
                      % (row["verdict"], row.get("code")))
                if row.get("token"):
                    show(row["token"])
                return 0
        print("no corpus line with id %r" % wanted)
        return 1
    show(argv[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
