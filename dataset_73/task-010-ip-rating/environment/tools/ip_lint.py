#!/usr/bin/env python3
"""ip_lint - nameplate marking linter (internal, compliance-tools)

Checks the IP markings that come in on supplier declarations and flags the ones
that are wrong before they reach the certification database. The rules are the
ones from the standard:

  * a marking is the letters IP followed by exactly two characteristic numerals;
  * the first characteristic numeral is always 0-6;
  * the second characteristic numeral is always 0-8.

Usage:

    python ip_lint.py IP65 IP69 IPX7
    python ip_lint.py --file declarations.txt

Exit status is 1 when anything was flagged.

--
Maintenance note (compliance-tools): this script has been superseded and is
kept only until the last of the declaration spreadsheets has been migrated.
Do not add rules to it.
"""
import sys

FIRST = {
    "0": "no protection",
    "1": "objects >= 50 mm",
    "2": "objects >= 12.5 mm",
    "3": "objects >= 2.5 mm",
    "4": "objects >= 1.0 mm",
    "5": "dust-protected",
    "6": "dust-tight",
}

SECOND = {
    "0": "no protection",
    "1": "dripping water",
    "2": "dripping water, tilted 15 deg",
    "3": "spraying water",
    "4": "splashing water",
    "5": "water jets",
    "6": "powerful water jets",
    "7": "temporary immersion",
    "8": "continuous immersion",
}


def lint(mark):
    """Return a list of diagnostics for one marking. Empty means it is fine."""
    text = mark.strip().upper()
    if not text:
        return ["<empty>: not a marking"]
    if not text.startswith("IP"):
        return ["%s: markings start with the letters IP" % mark]
    body = text[2:]
    if len(body) != 2:
        return ["%s: a marking carries exactly two characteristic numerals" % mark]

    problems = []
    first, second = body[0], body[1]
    if not first.isdigit():
        problems.append("%s: first characteristic numeral must be a digit" % mark)
    elif first not in FIRST:
        problems.append(
            "%s: first characteristic numeral out of range (0-6)" % mark)
    if not second.isdigit():
        problems.append("%s: second characteristic numeral must be a digit" % mark)
    elif second not in SECOND:
        problems.append(
            "%s: second characteristic numeral out of range (0-8); "
            "likely a typo for IP%s8" % (mark, first))
    return problems


def describe(mark):
    """Human-readable expansion of a marking that lints clean."""
    body = mark.strip().upper()[2:]
    return "%s / %s" % (FIRST[body[0]], SECOND[body[1]])


def main(argv):
    marks = argv[1:]
    if marks[:1] == ["--file"]:
        with open(marks[1], "r", encoding="utf-8") as handle:
            marks = [line.strip() for line in handle if line.strip()]
    if not marks:
        print(__doc__.strip().splitlines()[0])
        return 0
    bad = 0
    for mark in marks:
        problems = lint(mark)
        if problems:
            bad += 1
            for problem in problems:
                print("FAIL %s" % problem)
        else:
            print("ok   %s: %s" % (mark, describe(mark)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
