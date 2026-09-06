"""Deciding an assignment, and reporting what was decided."""
import json

from .bucket import in_traffic, pick_variant

ASSIGNED = "ASSIGNED"
EXCLUDED = "EXCLUDED"
NOT_IN_TRAFFIC = "NOT_IN_TRAFFIC"
STOPPED = "STOPPED"
NOT_STARTED = "NOT_STARTED"
MUTUALLY_EXCLUDED = "MUTUALLY_EXCLUDED"
UNKNOWN_EXPERIMENT = "UNKNOWN_EXPERIMENT"

STATE_REASON = {"stopped": STOPPED, "draft": NOT_STARTED}


class Service:
    def __init__(self, config):
        self.salt = config.get("salt", "")
        self.order = []            # experiments, as declared
        self.by_key = {}
        self.assignments = []
        self.errors = []
        self.reported_unknown = set()
        self.held = {}             # (user, exclusion group) -> experiment key

    def declare(self, record):
        self.order.append(record)
        self.by_key[record["key"]] = record

    def assign(self, record):
        user = record["user"]
        key = record["experiment"]
        experiment = self.by_key.get(key)

        if experiment is None:
            if key not in self.reported_unknown:
                self.reported_unknown.add(key)
                self.errors.append({"code": UNKNOWN_EXPERIMENT, "detail": key})
            return self._record(user, key, None, UNKNOWN_EXPERIMENT)

        reason = STATE_REASON.get(experiment["state"])
        if reason is not None:
            return self._record(user, key, None, reason)

        if user in (experiment.get("exclude") or []):
            return self._record(user, key, None, EXCLUDED)

        group = experiment.get("exclusion_group")
        # The gate comes first: somebody the traffic gate turned away was never
        # in the experiment at all, so they are still free for the next one in
        # the group. Doing it the other way round is defensible too; this way
        # round wastes less of the group.
        if not in_traffic(self.salt, key, user, experiment["traffic"]):
            return self._record(user, key, None, NOT_IN_TRAFFIC)

        if group is not None:
            holder = self.held.get((user, group))
            if holder is not None and holder != key:
                return self._record(user, key, None, MUTUALLY_EXCLUDED)

        variant = pick_variant(self.salt, key, user, experiment["variants"])
        if group is not None:
            self.held[(user, group)] = key
        return self._record(user, key, variant, ASSIGNED)

    def _record(self, user, key, variant, reason):
        self.assignments.append({"user": user, "experiment": key,
                                 "variant": variant, "reason": reason})

    def summary(self):
        rows = []
        for experiment in self.order:
            key = experiment["key"]
            mine = [entry for entry in self.assignments
                    if entry["experiment"] == key]
            rows.append({
                "experiment": key,
                "variants": [{"variant": variant["name"],
                              "count": sum(1 for entry in mine
                                           if entry["variant"] == variant["name"])}
                             for variant in experiment["variants"]],
                "unassigned": sum(1 for entry in mine if entry["variant"] is None),
            })
        return rows

    def report(self):
        return {"assignments": self.assignments, "summary": self.summary(),
                "errors": self.errors}


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("capture must begin with a config record")
    service = Service(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] == "experiment":
            service.declare(record)
        elif record["op"] == "assign":
            service.assign(record)
        else:
            raise ValueError("unknown op %r" % (record["op"],))
    return service.report()
