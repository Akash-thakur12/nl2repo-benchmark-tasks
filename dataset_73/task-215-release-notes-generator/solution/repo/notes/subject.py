"""Reading a commit (spec sections 2 and 3)."""
import re

CONVENTIONAL = re.compile(r"^([a-z]+)(?:\(([^)]+)\))?(!)?: (.*)$")   # 2.1
TRAILING_PR = re.compile(r"^(.*) \(#([0-9]+)\)$")                    # 2.4

BREAKING_FOOTERS = ("BREAKING CHANGE: ", "BREAKING-CHANGE: ")        # 3.2
REVERTS_FOOTER = "Reverts: "                                         # 5.4


class Subject:
    """What a conventional subject line says."""

    def __init__(self, type_, scope, bang, description):
        self.type = type_
        self.scope = scope
        self.bang = bang
        self.description = description


def read_subject(line):
    """2.1-2.3. None when the line is not conventional."""
    found = CONVENTIONAL.match(line)
    if found is None:
        return None
    type_, scope, bang, description = found.groups()
    description = description.strip()
    if not description:                                              # 2.3
        return None
    return Subject(type_, scope, bang is not None, description)


def strip_pull_request(description):
    """2.4. Only a reference at the very end is a reference."""
    found = TRAILING_PR.match(description)
    if found is None:
        return description, None
    return found.group(1).rstrip(), int(found.group(2))


def footer_lines(commit):
    """3.2. Trailing whitespace on a line is not significant; leading is."""
    return [line.rstrip() for line in (commit.get("body") or "").split("\n")]


def find_footer(commit, prefixes):
    for line in footer_lines(commit):
        for prefix in prefixes:
            if line.startswith(prefix):
                return line[len(prefix):].strip()
    return None


def breaking_note(commit):
    return find_footer(commit, BREAKING_FOOTERS)                     # 3.2, 3.3


def reverted_sha(commit):
    return find_footer(commit, (REVERTS_FOOTER,))                    # 5.4
