"""Reference model for the access review tool, following docs/review-spec.md
literally. Section numbers in comments refer to that document. This is the
authority for expected output; nothing is hardcoded.
"""
import collections
import json

APPROVED = "APPROVED"
REVOKED = "REVOKED"
STILL_INHERITED = "STILL_INHERITED"
UNREVIEWED = "UNREVIEWED"
AUTO_REVOKED = "AUTO_REVOKED"
TERMINATED = "TERMINATED"

GONE = (REVOKED, AUTO_REVOKED, TERMINATED)                      # 5.3


class Access:
    def __init__(self, user, entitlement, source, via):
        self.user = user
        self.entitlement = entitlement
        self.source = source
        self.via = via
        self.state = None
        self.also_from_group = False       # 4.2 a direct grant a group repeats

    def rendered(self):
        return {"user": self.user, "entitlement": self.entitlement,
                "source": self.source, "via": self.via, "state": self.state,
                "effective": self.state not in GONE}             # 8.1


class Review:
    def __init__(self, config):
        self.default_revoke = bool(config.get("default_revoke"))
        self.pairs = [list(pair) for pair in
                      config.get("separation_of_duties") or []]
        self.groups = {}
        self.group_order = []
        self.users = []
        self.by_name = {}
        self.decisions = []
        self.cycle_errors = []
        self.errors = []
        self.unknown_groups = set()
        self.access = collections.OrderedDict()   # user -> {entitlement: Access}

    # ------------------------------------------------------------ directory
    def add_group(self, record):
        self.groups[record["name"]] = record
        self.group_order.append(record["name"])

    def add_user(self, record):
        self.users.append(record)
        self.by_name[record["name"]] = record

    def add_decision(self, record):
        self.decisions.append(record)

    def _find_cycles(self):
        """1.5 every group that can reach itself, in directory order."""
        for name in self.group_order:
            seen = set()
            queue = collections.deque([name])
            reaches_itself = False
            while queue:
                current = queue.popleft()
                for member in self.groups.get(current, {}).get("members") or []:
                    if member == name:
                        reaches_itself = True
                    if member in seen or member not in self.groups:
                        continue
                    seen.add(member)
                    queue.append(member)
            if reaches_itself:
                self.cycle_errors.append({"code": "MEMBERSHIP_CYCLE",
                                          "detail": name})

    def _groups_of(self, user):
        """2.2 breadth first, each group reached once."""
        reached = []
        seen = set()
        queue = collections.deque(user.get("groups") or [])
        while queue:
            name = queue.popleft()
            if name in seen:
                continue
            seen.add(name)
            group = self.groups.get(name)
            if group is None:                                    # 1.4
                if name not in self.unknown_groups:
                    self.unknown_groups.add(name)
                    self.errors.append({"code": "UNKNOWN_GROUP", "detail": name})
                continue
            reached.append(group)
            queue.extend(group.get("members") or [])
        return reached

    def resolve(self):
        self._find_cycles()
        for user in self.users:                                  # 8.1 order
            name = user["name"]
            held = collections.OrderedDict()
            for entitlement in user.get("entitlements") or []:   # 2.3, 2.4
                if entitlement not in held:
                    held[entitlement] = Access(name, entitlement, "DIRECT", None)
            for group in self._groups_of(user):
                for entitlement in group.get("entitlements") or []:
                    if entitlement in held:
                        held[entitlement].also_from_group = True
                        continue
                    held[entitlement] = Access(name, entitlement, "GROUP",
                                               group["name"])
            self.access[name] = held

    # ------------------------------------------------------------ decisions
    def apply_decisions(self):
        settled = set()
        for record in self.decisions:                            # 3.1
            user = self.by_name.get(record["user"])
            if user is None:                                     # 3.2
                self.errors.append({"code": "UNKNOWN_USER",
                                    "detail": record["user"]})
                continue
            if user.get("terminated"):                           # 3.3
                self.errors.append({"code": "TERMINATED_USER",
                                    "detail": record["user"]})
                continue
            pair = "%s:%s" % (record["user"], record["entitlement"])
            entry = self.access[record["user"]].get(record["entitlement"])
            if entry is None:                                    # 3.4
                self.errors.append({"code": "NO_SUCH_ACCESS", "detail": pair})
                continue
            if pair in settled:                                  # 3.5
                self.errors.append({"code": "DUPLICATE_DECISION",
                                    "detail": pair})
                continue
            settled.add(pair)
            if record["verdict"] == "approve":                   # 4.1
                entry.state = APPROVED
            else:
                entry.state = self._revoked_state(entry, REVOKED)

    def _revoked_state(self, entry, plain):
        if entry.source == "GROUP":                              # 4.3
            return STILL_INHERITED
        if entry.also_from_group:                                # 4.2
            return STILL_INHERITED
        return plain

    def finish(self):
        for user in self.users:
            terminated = bool(user.get("terminated"))
            for entry in self.access[user["name"]].values():
                if terminated:                                   # 6.1
                    entry.state = TERMINATED
                    continue
                if entry.state is not None:
                    continue
                if self.default_revoke:                          # 5.2
                    entry.state = self._revoked_state(entry, AUTO_REVOKED)
                else:                                            # 5.1
                    entry.state = UNREVIEWED

    # ------------------------------------------------------------- report
    def violations(self):
        found = []
        for user in self.users:                                  # 7.3
            effective = {entry.entitlement
                         for entry in self.access[user["name"]].values()
                         if entry.state not in GONE}
            for pair in self.pairs:                              # 7.2
                if pair[0] in effective and pair[1] in effective:
                    found.append({"user": user["name"],
                                  "entitlements": list(pair)})
        return found

    def report(self):
        return {
            "access": [entry.rendered() for user in self.users
                       for entry in self.access[user["name"]].values()],  # 8.1
            "violations": self.violations(),                              # 8.2
            "errors": self.cycle_errors + self.errors,                    # 8.3
        }


def replay(records):
    review = Review(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] == "group":
            review.add_group(record)
        elif record["op"] == "user":
            review.add_user(record)
        elif record["op"] == "decision":
            review.add_decision(record)
        else:
            raise ValueError("unknown op %r" % (record["op"],))
    review.resolve()
    review.apply_decisions()
    review.finish()
    return review.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("review must begin with a config record")
    return replay(records)
