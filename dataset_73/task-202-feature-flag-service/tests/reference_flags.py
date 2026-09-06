"""Reference model for flag evaluation, following docs/flag-spec.md v3 literally.

Section numbers in comments refer to that document; incident numbers refer to
the audit write-ups in docs/incidents/ and docs/CHANGELOG.md that the
specification delegates to. This is the authority for expected output; nothing
is hardcoded.
"""
import hashlib
import json

NUMBER = (int, float)

#: 4.3 / INC-4530: the bucket is not covered by the rollout at all.
UNALLOCATED = object()


def bucket_of(flag_key, salt, user_key):
    """4.1: the reduction pinned by docs/fixtures/bucketing.csv.

    First eight hex characters of the sha256 digest, modulo 10000. Checked
    against all 24 fixture rows by tools/check_fixture.py.
    """
    raw = "%s:%s:%s" % (flag_key, salt, user_key)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 10000


def _is_number(value):
    return isinstance(value, NUMBER) and not isinstance(value, bool)


def rule_matches(rule, user):
    attribute = rule["attribute"]
    if attribute not in user:            # 3.1: absent never matches
        return False
    value = user[attribute]
    op = rule["operator"]
    values = rule["values"]

    if op == "in":                       # 3.3: exact type equality
        return any(_same(value, v) for v in values)
    if op == "not_in":
        return not any(_same(value, v) for v in values)
    if op in ("starts_with", "contains"):
        if not isinstance(value, str):   # 3.4
            return False
        if op == "starts_with":
            return any(isinstance(v, str) and value.startswith(v) for v in values)
        return any(isinstance(v, str) and v in value for v in values)
    if op in ("gt", "lt"):
        if not _is_number(value) or not values or not _is_number(values[0]):
            return False                 # 3.5
        return value > values[0] if op == "gt" else value < values[0]
    raise ValueError("unknown operator %r" % (op,))


def _same(a, b):
    """3.3: a bool is never equal to a number, and types must agree."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if _is_number(a) and _is_number(b):
        return a == b
    return type(a) is type(b) and a == b


def pick_rollout(rollout, bucket):
    """4.3: cumulative weights, first running total strictly above the bucket.

    INC-4530: weights may sum to less than 10000, and a bucket at or above the
    total is not a rollout result - it does not clamp to the last entry.
    """
    total = 0
    for entry in rollout:
        total += entry["weight"]
        if bucket < total:
            return entry["variant"]
    return UNALLOCATED


class CycleDetected(Exception):
    """5.1 / INC-4602: abandons the whole evaluation, not one prerequisite."""


class Registry:
    def __init__(self):
        self.flags = {}
        self.salts = {}          # INC-4471: salt in force, keyed by flag key

    def define(self, flag):
        # INC-4471: the salt is allocated when the key is created and pinned
        # for the lifetime of the key; a later definition's salt is ignored.
        self.salts.setdefault(flag["key"], flag["salt"])
        self.flags[flag["key"]] = flag

    def delete(self, key):
        self.flags.pop(key, None)
        self.salts.pop(key, None)            # deleting releases the seed

    def evaluate(self, key, user):
        """Entry point: only the entry flag reports a cycle (INC-4602)."""
        try:
            return self._resolve(key, user, ())
        except CycleDetected:
            flag = self.flags.get(key)
            if flag is None:                                # not reachable
                return None, "FLAG_NOT_FOUND"
            return flag["off_variant"], "CYCLE"             # 5.1

    def _resolve(self, key, user, stack):
        flag = self.flags.get(key)
        if flag is None:                                    # 2.1
            return None, "FLAG_NOT_FOUND"
        if key in stack:                                    # 5.1
            raise CycleDetected(key)
        if not flag["enabled"]:                             # 2.2
            return flag["off_variant"], "OFF"

        for prereq in flag.get("prerequisites", []):        # 2.3
            variant, _reason = self._resolve(prereq["flag"], user, stack + (key,))
            if variant != prereq["variant"]:
                return flag["off_variant"], "PREREQUISITE_FAILED"

        bucket = bucket_of(key, self.salts[key], user["key"])   # 4.2, 4.4

        for rule in flag.get("rules", []):                  # 2.4: first match wins
            if not rule_matches(rule, user):
                continue
            if "variant" in rule:
                return rule["variant"], "RULE_MATCH"
            picked = pick_rollout(rule["rollout"], bucket)
            if picked is UNALLOCATED:                       # INC-4530
                continue
            return picked, "RULE_ROLLOUT"

        return flag["default_variant"], "DEFAULT"           # 2.5


def parse_scenario(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def replay(records):
    reg = Registry()
    evaluations = []
    for record in records:
        op = record["op"]
        if op == "end":
            break
        if op in ("define", "update"):                      # 6.1
            reg.define(record["flag"])
        elif op == "delete":
            reg.delete(record["flag"])
        elif op == "evaluate":
            variant, reason = reg.evaluate(record["flag"], record["user"])
            evaluations.append({"flag": record["flag"], "user": record["user"]["key"],
                                "variant": variant, "reason": reason})
        else:
            raise ValueError("unknown op %r" % (op,))
    return {"evaluations": evaluations, "flags": sorted(reg.flags)}


def replay_text(text):
    return replay(parse_scenario(text))
