"""Reference model for the release notes generator, following
docs/release-notes-spec.md literally. Section numbers in comments refer to that
document. This is the authority for expected output; nothing is hardcoded.
"""
import json
import re

SUBJECT = re.compile(r"^([a-z]+)(?:\(([^)]+)\))?(!)?: (.*)$")   # 2.1
PR_SUFFIX = re.compile(r"^(.*) \(#(\d+)\)$")                    # 2.4
BREAKING_PREFIXES = ("BREAKING CHANGE: ", "BREAKING-CHANGE: ")   # 3.2
REVERTS_PREFIX = "Reverts: "                                     # 5.4

OTHER = "Other"


class Entry:
    def __init__(self, commit, type_, scope, description, pr, breaking, note):
        self.sha = commit["sha"]
        self.author = commit.get("author")
        self.type = type_
        self.scope = scope
        self.description = description
        self.pr = pr
        self.breaking = breaking
        self.note = note

    def key(self):
        return (self.type, self.scope, self.description)          # 5.3

    def as_json(self):
        return {"sha": self.sha, "type": self.type, "scope": self.scope,
                "description": self.description, "pr": self.pr,
                "breaking": self.breaking}                        # 9.3


def parse_subject(subject):
    """2.1-2.3. Returns (type, scope, bang, description) or None."""
    match = SUBJECT.match(subject)
    if match is None:
        return None
    type_, scope, bang, description = match.groups()
    description = description.strip()
    if not description:                                           # 2.3
        return None
    return type_, scope, bang is not None, description


def split_pr(description):
    """2.4. Returns (description, pr or None)."""
    match = PR_SUFFIX.match(description)
    if match is None:
        return description, None
    return match.group(1).rstrip(), int(match.group(2))


def body_lines(commit):
    body = commit.get("body") or ""
    return [line.rstrip() for line in body.split("\n")]            # 3.2


def breaking_note(commit):
    """3.2, 3.3. Returns the note text, or None when the body says nothing."""
    for line in body_lines(commit):
        for prefix in BREAKING_PREFIXES:
            if line.startswith(prefix):
                return line[len(prefix):].strip()
    return None


def reverts_sha(commit):
    """5.4. Returns the referenced sha, or None."""
    for line in body_lines(commit):
        if line.startswith(REVERTS_PREFIX):
            return line[len(REVERTS_PREFIX):].strip()
    return None


class Notes:
    def __init__(self, config):
        self.previous = config["previous_version"]
        self.sections = list(config["sections"])
        self.included = list(config["include_types"])

        self.entries = []          # surviving, in history order
        self.by_sha = {}
        self.skipped = {}          # sha -> reason
        self.errors = []
        self.order = []            # every sha, in history order

    # -------------------------------------------------------------- helpers
    def _skip(self, commit, reason):
        # 8.1 one reason per commit, the first one decided
        self.skipped.setdefault(commit["sha"], reason)

    def _drop(self, entry):
        self.entries.remove(entry)
        self.by_sha.pop(entry.sha, None)

    # -------------------------------------------------------------- commits
    def add(self, commit):
        self.order.append(commit["sha"])
        parsed = parse_subject(commit["subject"])
        if parsed is None:                                        # 2.2, 2.3
            self._skip(commit, "UNCONVENTIONAL")
            return
        type_, scope, bang, description = parsed

        if type_ not in self.included:                            # 5.2, 3.4
            self._skip(commit, "TYPE_EXCLUDED")
            return

        if type_ == "revert":                                     # 5.4
            self._revert(commit)
            return

        description, pr = split_pr(description)                   # 2.4
        if commit.get("merged_pr") is not None:                   # 2.5
            pr = commit["merged_pr"]

        note = breaking_note(commit)
        breaking = bang or note is not None                       # 3.1, 3.2
        entry = Entry(commit, type_, scope, description, pr, breaking,
                      note if note is not None else description)  # 3.3

        for existing in self.entries:
            if existing.key() == entry.key():                     # 5.3
                self._skip(commit, "DUPLICATE")
                return

        self.entries.append(entry)
        self.by_sha[entry.sha] = entry

    def _revert(self, commit):
        self._skip(commit, "REVERT")                              # 5.5-5.7
        sha = reverts_sha(commit)
        if sha is None:
            self.errors.append({"code": "MALFORMED_REVERT",
                                "detail": commit["sha"]})         # 5.7
            return
        target = self.by_sha.get(sha)
        if target is None:
            self.errors.append({"code": "UNKNOWN_REVERT", "detail": sha})  # 5.6
            return
        self._drop(target)
        self.skipped[target.sha] = "REVERTED"                     # 5.5

    # --------------------------------------------------------------- report
    def _bump(self):
        if any(entry.breaking for entry in self.entries):         # 4.2
            return "major"
        if any(entry.type == "feat" for entry in self.entries):
            return "minor"
        if self.entries:
            return "patch"
        return "none"

    def _version(self, bump):
        major, minor, patch = (int(part) for part in self.previous.split("."))
        if bump == "major":
            if major == 0:                                        # 4.4
                return "0.%d.0" % (minor + 1)
            return "%d.0.0" % (major + 1)
        if bump == "minor":                                       # 4.3
            return "%d.%d.0" % (major, minor + 1)
        if bump == "patch":
            return "%d.%d.%d" % (major, minor, patch + 1)
        return self.previous

    def _sections(self):
        out = []
        placed = set()
        for section in self.sections:                             # 6.1, 6.2
            entries = [e for e in self.entries if e.type == section["type"]]
            placed.add(section["type"])
            if entries:
                out.append({"title": section["title"],
                            "entries": [e.as_json() for e in entries]})
        rest = [e for e in self.entries if e.type not in placed]  # 6.3
        if rest:
            out.append({"title": OTHER,
                        "entries": [e.as_json() for e in rest]})
        return out

    def report(self):
        bump = self._bump()
        contributors = []
        for entry in self.entries:                                # 7.1, 7.2
            if entry.author is not None and entry.author not in contributors:
                contributors.append(entry.author)
        return {
            "version": self._version(bump),                       # 9.1
            "bump": bump,                                         # 9.2
            "sections": self._sections(),                         # 9.3
            "breaking": [{"sha": e.sha, "note": e.note}
                         for e in self.entries if e.breaking],     # 9.4
            "contributors": contributors,                          # 9.5
            "skipped": [{"sha": sha, "reason": self.skipped[sha]}  # 8.1
                        for sha in self.order if sha in self.skipped],
            "errors": self.errors,                                 # 8.2
        }


def replay(records):
    notes = Notes(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] != "commit":
            raise ValueError("unknown op %r" % (record["op"],))
        notes.add(record)
    return notes.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("history must begin with a config record")
    return replay(records)
