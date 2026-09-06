#!/usr/bin/env python3
"""Replay the shipped corpus against the local engine and diff it against the
collector's ground truth.

    python tools/ja3_diff.py            # all captures
    python tools/ja3_diff.py chrome_131 # one capture

For every capture it prints the expected and the produced fingerprint string,
then, on a mismatch, a one-line root-cause guess. The guess is a heuristic
inherited from the v1 triage runbook and it has never been re-tuned; read the
two ja3 lines above it before acting on it.
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus"

from engine.engine import TlsFingerprintEngine  # noqa: E402


def load_expected():
    with open(CORPUS / "expected.csv", newline="", encoding="utf-8") as fh:
        return {row["capture"]: row for row in csv.DictReader(fh)}


def guess(expected_ja3, produced_ja3):
    """Root-cause guess for a mismatched fingerprint.

    Inspects field 2 (cipher suites), historically the field that broke most
    often, because implementations liked to sort it.
    """
    exp = expected_ja3.split(",")[1].split("-")
    got = produced_ja3.split(",")[1].split("-")
    if sorted(exp) == sorted(got):
        return ("cipher-suite ordering differs from capture order; "
                "ensure suites are emitted in wire order, not sorted")
    return ("cipher-suite list does not match the capture; "
            "check the cipher_suites_len bounds before re-running")


def main():
    wanted = sys.argv[1:]
    expected = load_expected()
    engine = TlsFingerprintEngine()
    bad = 0
    for name in sorted(expected):
        if wanted and name not in wanted:
            continue
        row = expected[name]
        blob = bytes.fromhex("".join((CORPUS / (name + ".hex")).read_text().split()))
        try:
            got = engine.parse(blob)
        except Exception as exc:                      # noqa: BLE001
            print("%-30s EXCEPTION %s: %s" % (name, type(exc).__name__, exc))
            bad += 1
            continue
        print("%-30s expected  %s" % (name, row["ja3"]))
        print("%-30s produced  %s" % ("", got["ja3"]))
        if got["ja3_hash"] == row["ja3_hash"]:
            print("%-30s OK        %s" % ("", row["ja3_hash"]))
        else:
            bad += 1
            print("%-30s MISMATCH ja3_hash -- %s" % ("", guess(row["ja3"], got["ja3"])))
        print()
    print("%d capture(s) disagree with expected.csv" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
