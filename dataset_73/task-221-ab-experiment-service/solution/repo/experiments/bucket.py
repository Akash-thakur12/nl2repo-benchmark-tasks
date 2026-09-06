"""Turning a user and an experiment into a number nobody can argue with.

The brief only asks that the answer be stable: the same person, the same
experiment, the same salt, the same result, on any machine and on any day. A
hash of the three, read as an integer, is the usual way to get that, and it is
what this does. Python's own hash() would not do - it is salted per process.
"""
import hashlib

#: How finely the space is divided. Ten thousand buckets means a weight of one
#: per cent is a hundred buckets, which is plenty for the experiments we run.
BUCKETS = 10000


def bucket(salt, experiment, user, purpose):
    """A stable number in [0, BUCKETS). `purpose` keeps the traffic gate and the
    variant choice from being the same draw, so an experiment on fifty per cent
    traffic does not put everybody who got in into the same variant."""
    material = "%s|%s|%s|%s" % (salt, experiment, user, purpose)
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % BUCKETS


def in_traffic(salt, experiment, user, percent):
    if percent >= 100:
        return True
    if percent <= 0:
        return False
    return bucket(salt, experiment, user, "traffic") < percent * BUCKETS // 100


def pick_variant(salt, experiment, user, variants):
    """The first variant whose share of the space covers the user's bucket. A
    variant weighted zero covers nothing, so it is never chosen."""
    draw = bucket(salt, experiment, user, "variant")
    edge = 0
    for variant in variants:
        edge += variant["weight"] * BUCKETS // 100
        if draw < edge:
            return variant["name"]
    return variants[-1]["name"]
