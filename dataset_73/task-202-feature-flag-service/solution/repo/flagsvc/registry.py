"""Flag storage and the evaluation order (spec sections 2, 5, 6)."""
from .bucketing import UNALLOCATED, bucket_for, select_variant
from .operators import matches


class Result(tuple):
    """(variant, reason) with names, so call sites read clearly."""
    __slots__ = ()

    def __new__(cls, variant, reason):
        return super().__new__(cls, (variant, reason))

    @property
    def variant(self):
        return self[0]

    @property
    def reason(self):
        return self[1]


class CycleDetected(Exception):
    """5.1 / INC-4602: the whole evaluation is abandoned, not one prerequisite.

    Raised where the loop is seen and caught at the entry flag, which is the
    only flag that reports. Carrying this as an exception rather than a return
    value is the point: no intermediate prerequisite comparison ever sees the
    cycling flag's variant, so a cycling flag whose off_variant happens to equal
    the required variant cannot masquerade as a satisfied prerequisite.
    """


class Registry:
    def __init__(self):
        self._flags = {}
        self._salts = {}

    # 6.1: define and update are the same operation, delete is tolerant
    def put(self, definition):
        key = definition["key"]
        # CHANGELOG v3.0 / INC-4471: the bucketing salt is allocated when the
        # key is created and pinned for the lifetime of the key. A later
        # definition's salt is recorded but not put in force.
        self._salts.setdefault(key, definition["salt"])
        self._flags[key] = definition

    def drop(self, key):
        self._flags.pop(key, None)
        self._salts.pop(key, None)   # deleting the key releases the seed

    @property
    def keys(self):
        return sorted(self._flags)

    def salt_in_force(self, key):
        """INC-4471: the salt recorded when the key was first defined."""
        return self._salts.get(key)

    def evaluate(self, key, user):
        """Entry point. The entry flag is the only flag that reports a cycle."""
        try:
            return self._evaluate(key, user, ())
        except CycleDetected:
            flag = self._flags.get(key)
            if flag is None:                                # unreachable: a
                return Result(None, "FLAG_NOT_FOUND")       # cycle needs a flag
            return Result(flag["off_variant"], "CYCLE")     # 5.1

    def _evaluate(self, key, user, in_progress):
        flag = self._flags.get(key)
        if flag is None:                                    # 2.1
            return Result(None, "FLAG_NOT_FOUND")
        if key in in_progress:                              # 5.1
            raise CycleDetected(key)
        if not flag["enabled"]:                             # 2.2 off, not default
            return Result(flag["off_variant"], "OFF")

        unmet = self._first_unmet_prerequisite(flag, user, in_progress + (key,))
        if unmet:                                           # 2.3
            return Result(flag["off_variant"], "PREREQUISITE_FAILED")

        # 4.4: one bucket per evaluation, shared by every rollout
        bucket = bucket_for(key, self._salts[key], user["key"])

        for rule in flag.get("rules", []):                  # 2.4 first match wins
            if not matches(rule, user):
                continue
            if "variant" in rule:
                return Result(rule["variant"], "RULE_MATCH")
            picked = select_variant(rule["rollout"], bucket)
            if picked is UNALLOCATED:
                continue         # INC-4530: not a rollout result, not decisive
            return Result(picked, "RULE_ROLLOUT")

        return Result(flag["default_variant"], "DEFAULT")   # 2.5

    def _first_unmet_prerequisite(self, flag, user, in_progress):
        for prerequisite in flag.get("prerequisites", []):
            result = self._evaluate(prerequisite["flag"], user, in_progress)
            if result.variant != prerequisite["variant"]:
                return prerequisite
        return None
