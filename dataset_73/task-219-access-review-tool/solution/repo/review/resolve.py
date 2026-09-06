"""Resolving the review (spec sections 3 to 8)."""
import json

from .directory import Directory

APPROVED = "APPROVED"
REVOKED = "REVOKED"
STILL_INHERITED = "STILL_INHERITED"
UNREVIEWED = "UNREVIEWED"
AUTO_REVOKED = "AUTO_REVOKED"
TERMINATED = "TERMINATED"

#: 5.3 the states that mean the access is not there any more
LOST = frozenset((REVOKED, AUTO_REVOKED, TERMINATED))


class Grant:
    """One user's hold on one entitlement."""

    def __init__(self, user, entitlement, source, via):
        self.user = user
        self.entitlement = entitlement
        self.source = source
        self.via = via
        self.repeated_by_group = False
        self.state = None

    def effective(self):
        return self.state not in LOST

    def rendered(self):
        return {"user": self.user, "entitlement": self.entitlement,
                "source": self.source, "via": self.via, "state": self.state,
                "effective": self.effective()}                      # 8.1


class Resolver:
    def __init__(self, config):
        self.revoke_by_default = bool(config.get("default_revoke"))
        self.conflicts = [list(pair)
                          for pair in config.get("separation_of_duties") or []]
        self.directory = Directory()
        self.decisions = []
        self.loop_errors = []
        self.errors = []
        self.missing_groups = set()
        self.grants = {}                  # user name -> [Grant], in order

    # --------------------------------------------------------------- intake
    def add_group(self, record):
        self.directory.add_group(record)

    def add_user(self, record):
        self.directory.add_user(record)

    def add_decision(self, record):
        self.decisions.append(record)

    def _error(self, code, detail):
        self.errors.append({"code": code, "detail": detail})

    # ------------------------------------------------------------ resolving
    def build(self):
        for name in self.directory.looping_groups():                # 1.5
            self.loop_errors.append({"code": "MEMBERSHIP_CYCLE", "detail": name})

        def missing(name):
            if name not in self.missing_groups:                     # 1.4
                self.missing_groups.add(name)
                self._error("UNKNOWN_GROUP", name)

        for user in self.directory.users:
            held = []
            index = {}
            for entitlement in user.get("entitlements") or []:       # 2.3, 2.4
                if entitlement in index:
                    continue
                grant = Grant(user["name"], entitlement, "DIRECT", None)
                index[entitlement] = grant
                held.append(grant)
            for group in self.directory.membership(user, missing):
                for entitlement in group.get("entitlements") or []:
                    if entitlement in index:
                        index[entitlement].repeated_by_group = True
                        continue
                    grant = Grant(user["name"], entitlement, "GROUP",
                                  group["name"])
                    index[entitlement] = grant
                    held.append(grant)
            self.grants[user["name"]] = held

    def _held(self, user_name, entitlement):
        for grant in self.grants[user_name]:
            if grant.entitlement == entitlement:
                return grant
        return None

    def review(self):
        decided = set()
        for record in self.decisions:                                # 3.1
            who = record["user"]
            user = self.directory.user_by_name.get(who)
            if user is None:                                         # 3.2
                self._error("UNKNOWN_USER", who)
                continue
            if user.get("terminated"):                               # 3.3
                self._error("TERMINATED_USER", who)
                continue
            pair = "%s:%s" % (who, record["entitlement"])
            grant = self._held(who, record["entitlement"])
            if grant is None:                                        # 3.4
                self._error("NO_SUCH_ACCESS", pair)
                continue
            if pair in decided:                                      # 3.5
                self._error("DUPLICATE_DECISION", pair)
                continue
            decided.add(pair)
            grant.state = (APPROVED if record["verdict"] == "approve"
                           else self._after_revoke(grant, REVOKED))  # 4.1, 4.2

    @staticmethod
    def _after_revoke(grant, taken):
        # 4.2, 4.3 a review can only take away what the user holds on their own
        if grant.source == "GROUP" or grant.repeated_by_group:
            return STILL_INHERITED
        return taken

    def settle(self):
        for user in self.directory.users:
            left = bool(user.get("terminated"))
            for grant in self.grants[user["name"]]:
                if left:                                             # 6.1
                    grant.state = TERMINATED
                elif grant.state is None:
                    grant.state = (self._after_revoke(grant, AUTO_REVOKED)
                                   if self.revoke_by_default          # 5.2
                                   else UNREVIEWED)                   # 5.1

    # --------------------------------------------------------------- report
    def _violations(self):
        found = []
        for user in self.directory.users:                            # 7.3
            standing = {grant.entitlement
                        for grant in self.grants[user["name"]]
                        if grant.effective()}
            for pair in self.conflicts:                              # 7.2
                if standing.issuperset(pair):
                    found.append({"user": user["name"],
                                  "entitlements": list(pair)})
        return found

    def report(self):
        return {
            "access": [grant.rendered() for user in self.directory.users
                       for grant in self.grants[user["name"]]],      # 8.1
            "violations": self._violations(),                        # 8.2
            "errors": self.loop_errors + self.errors,                # 8.3
        }


INTAKE = {"group": "add_group", "user": "add_user", "decision": "add_decision"}


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("review must begin with a config record")
    resolver = Resolver(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        handler = INTAKE.get(record["op"])
        if handler is None:
            raise ValueError("unknown op %r" % (record["op"],))
        getattr(resolver, handler)(record)
    resolver.build()
    resolver.review()
    resolver.settle()
    return resolver.report()
