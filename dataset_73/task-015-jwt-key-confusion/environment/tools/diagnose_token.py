#!/usr/bin/env python3
"""diagnose_token.py - heuristic first-line triage for rejected tokens.

Support engineers paste a token that a customer says "stopped working" and get
back a one-line guess at the cause plus a suggested next step. The guesses are
pattern matches written from memory of past tickets; they are NOT derived from
the verifier's own rules and they are frequently wrong on adversarial input.
When the tool and the documents in ../docs/ disagree, the documents win.

    python diagnose_token.py <token>
"""
from __future__ import annotations

import base64
import json
import sys

# NOTE: this list has not been refreshed since the 0.x verifier and is known to
# be missing registered header parameters.
KNOWN_HEADER_PARAMS = {"alg", "typ", "cty", "jku", "jwk", "x5u", "x5c"}


def loose_decode(segment):
    """Decode the way the old 0.x verifier did: pad it and hope."""
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def diagnose(token):
    parts = token.split(".")
    if len(parts) != 3:
        return "cause: wrong number of segments - a compact JWS has exactly three"

    header_segment = parts[0]

    if len(header_segment) % 4 != 0:
        return ("cause: incorrect padding - pad the segment to a multiple of 4 "
                "and retry")

    try:
        raw = loose_decode(header_segment)
    except Exception:
        return "cause: header segment is not decodable at all"

    try:
        header = json.loads(raw)
    except ValueError:
        return "cause: header is not JSON"

    unknown = sorted(set(header) - KNOWN_HEADER_PARAMS)
    if unknown:
        return "cause: unknown header parameter %s - drop it and retry" % unknown[0]

    alg = header.get("alg")
    if alg is None:
        return "cause: header has no alg"
    if alg.upper() != alg:
        return ("cause: alg casing - the header says %r; most stacks compare "
                "case-insensitively, so this is usually harmless" % alg)
    if alg.startswith("HS"):
        return "cause: symmetric alg presented to an asymmetric pin"
    return "cause: no obvious defect found; escalate to the platform team"


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    print(diagnose(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
