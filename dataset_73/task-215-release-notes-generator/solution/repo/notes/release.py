"""Turning a range of commits into release notes (spec sections 5 to 9)."""
import json

from .subject import breaking_note, read_subject, reverted_sha, strip_pull_request
from .version import apply_bump, choose_bump

OTHER_TITLE = "Other"

UNCONVENTIONAL = "UNCONVENTIONAL"
TYPE_EXCLUDED = "TYPE_EXCLUDED"
REVERT = "REVERT"
REVERTED = "REVERTED"
DUPLICATE = "DUPLICATE"


class Entry:
    """A surviving commit, as the notes will show it."""

    def __init__(self, commit, subject, description, pr, breaking, note):
        self.sha = commit["sha"]
        self.author = commit.get("author")
        self.type = subject.type
        self.scope = subject.scope
        self.description = description
        self.pr = pr
        self.breaking = breaking
        self.note = note

    @property
    def identity(self):
        return (self.type, self.scope, self.description)             # 5.3

    def rendered(self):
        return {"sha": self.sha, "type": self.type, "scope": self.scope,
                "description": self.description, "pr": self.pr,
                "breaking": self.breaking}                           # 9.3


class Release:
    def __init__(self, config):
        self.previous = config["previous_version"]
        self.section_config = list(config["sections"])
        self.included = set(config["include_types"])

        self.living = []            # entries that have survived so far
        self.by_sha = {}
        self.read_order = []        # every sha, in history order
        self.reasons = {}           # sha -> why it is not in the notes
        self.errors = []

    # -------------------------------------------------------------- reading
    def read(self, commit):
        self.read_order.append(commit["sha"])
        subject = read_subject(commit["subject"])
        if subject is None:                                          # 2.2, 2.3
            self._set_reason(commit["sha"], UNCONVENTIONAL)
            return

        if subject.type not in self.included:                        # 5.2, 3.4
            self._set_reason(commit["sha"], TYPE_EXCLUDED)
            return

        if subject.type == "revert":                                 # 5.4
            self._apply_revert(commit)
            return

        self._collect(commit, subject)

    def _set_reason(self, sha, reason):
        # 8.1 a commit is skipped for exactly one reason, the first decided
        self.reasons.setdefault(sha, reason)

    def _collect(self, commit, subject):
        description, pr = strip_pull_request(subject.description)    # 2.4
        merged = commit.get("merged_pr")
        if merged is not None:                                       # 2.5
            pr = merged

        note = breaking_note(commit)
        entry = Entry(commit, subject, description, pr,
                      subject.bang or note is not None,              # 3.1, 3.2
                      description if note is None else note)         # 3.3

        if any(other.identity == entry.identity for other in self.living):
            self._set_reason(commit["sha"], DUPLICATE)               # 5.3
            return

        self.living.append(entry)
        self.by_sha[entry.sha] = entry

    def _apply_revert(self, commit):
        self._set_reason(commit["sha"], REVERT)                      # 5.5-5.7
        target_sha = reverted_sha(commit)
        if target_sha is None:
            self.errors.append({"code": "MALFORMED_REVERT",
                                "detail": commit["sha"]})            # 5.7
            return
        target = self.by_sha.get(target_sha)                         # 5.8
        if target is None:
            self.errors.append({"code": "UNKNOWN_REVERT",
                                "detail": target_sha})               # 5.6
            return
        self.living.remove(target)
        del self.by_sha[target_sha]
        self.reasons[target_sha] = REVERTED                          # 5.5

    # --------------------------------------------------------------- output
    def _sections(self):
        rendered = []
        claimed = set()
        for section in self.section_config:                          # 6.1
            claimed.add(section["type"])
            entries = [e for e in self.living if e.type == section["type"]]
            if not entries:
                continue
            rendered.append({"title": section["title"],
                             "entries": [e.rendered() for e in entries]})  # 6.2
        leftover = [e for e in self.living if e.type not in claimed]
        if leftover:                                                 # 6.3
            rendered.append({"title": OTHER_TITLE,
                             "entries": [e.rendered() for e in leftover]})
        return rendered

    def _contributors(self):
        names = []
        for entry in self.living:                                    # 7.1, 7.2
            if entry.author is not None and entry.author not in names:
                names.append(entry.author)
        return names

    def report(self):
        bump = choose_bump(self.living)
        return {
            "version": apply_bump(self.previous, bump),              # 9.1
            "bump": bump,                                            # 9.2
            "sections": self._sections(),                            # 9.3
            "breaking": [{"sha": e.sha, "note": e.note}
                         for e in self.living if e.breaking],        # 9.4
            "contributors": self._contributors(),                    # 9.5
            "skipped": [{"sha": sha, "reason": self.reasons[sha]}    # 8.1
                        for sha in self.read_order if sha in self.reasons],
            "errors": self.errors,                                   # 8.2
        }


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("history must begin with a config record")
    release = Release(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] != "commit":
            raise ValueError("unknown op %r" % (record["op"],))
        release.read(record)
    return release.report()
