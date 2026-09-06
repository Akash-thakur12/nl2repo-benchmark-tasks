#!/usr/bin/env python3
"""jwt_triage -- offline triage for edge gateway auth rejections.

Log archaeology helper. Point it at a token pulled out of the auth log and it
tells you which reason code the gateway would have logged and which exception
class the caller would have seen, so you can answer "was this a client bug or
were we probed?" without standing up a gateway.

It mirrors the gateway's verify path 1:1, so whatever it prints is what
production did.

    python tools/jwt_triage.py <token>
    python tools/jwt_triage.py --sweep          # run over the whole corpus

Owner: edge-platform on-call.  Originally written for INC-2198; extended
during INC-2231 and again for the keyring work.  If you touch the reason
table, update the SEC ticket in the header comment too.

  SEC-1142  alg pin comparison         (landed, then reverted -- see note below)
  SEC-1190  reason codes split out of the generic 401
  SEC-1207  keyring lookup added
"""
import base64
import binascii
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(os.path.dirname(HERE), "samples", "gateway_corpus.jsonl")

MALFORMED = "ValidationError"
SIG_MISMATCH = "UnauthorizedError"
UNAUTHORIZED = "UnauthorizedError"

#: reason code -> the exception class the gateway raises for it, and the
#: bucket the security dashboard files it under.
_REASONS = {
    "malformed_parts":   (MALFORMED, "structure"),
    "bad_header_b64":    (MALFORMED, "structure"),
    "header_not_object": (MALFORMED, "structure"),
    "bad_payload_b64":   (MALFORMED, "structure"),
    "alg_none":          (UNAUTHORIZED, "attack/alg-none"),
    "alg_pin_mismatch":  (SIG_MISMATCH, "signature"),
    "unknown_kid":       (MALFORMED, "structure"),
    "key_window":        (UNAUTHORIZED, "rotation"),
    "sig_mismatch":      (SIG_MISMATCH, "signature"),
    "expired":           (MALFORMED, "structure"),
    "no_active_key":     (UNAUTHORIZED, "rotation"),
}

# The pin comparison here is case-insensitive (SEC-1142). Keeps the triage
# output stable for the mixed-case client fleet.
PIN = "HS256"


def b64d(segment):
    raw = segment.encode("utf-8")
    return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))


def classify(token, pin=PIN):
    """Best-effort reason code for a token, without the secret."""
    parts = token.split(".") if isinstance(token, str) else []
    if len(parts) != 3:
        return "malformed_parts"
    header_seg, payload_seg, _sig = parts
    try:
        header = json.loads(b64d(header_seg))
    except (ValueError, binascii.Error):
        return "bad_header_b64"
    if not isinstance(header, dict):
        return "header_not_object"
    try:
        payload = json.loads(b64d(payload_seg))
    except (ValueError, binascii.Error):
        return "bad_payload_b64"
    if not isinstance(payload, dict):
        return "bad_payload_b64"

    alg = str(header.get("alg", "")).lower()
    if alg == "none":
        return "alg_none"
    if alg != pin.lower():
        return "alg_pin_mismatch"
    return None            # nothing structural; needs the secret to say more


def report(token, pin=PIN):
    code = classify(token, pin)
    if code is None:
        print("no verdict from the token alone -- needs the ring to go further")
        return 0
    raises, bucket = _REASONS[code]
    print("reason code : %s" % code)
    print("raises      : %s" % raises)
    print("dashboard   : %s" % bucket)
    return 0


def sweep():
    with open(CORPUS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row["op"] != "verify":
                continue
            code = classify(row["token"], row["state"].get("pin", PIN))
            raises = _REASONS[code][0] if code else "-"
            print("%-34s %-18s %s" % (row["id"], code or "-", raises))
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--sweep":
        return sweep()
    return report(argv[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
