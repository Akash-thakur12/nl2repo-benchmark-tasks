"""Stable bucketing and rollout selection (spec section 4)."""
import hashlib

BUCKETS = 10000
DIGEST_CHARS = 8

#: Returned by :func:`select_variant` when the bucket is not covered by the
#: rollout at all. It is deliberately not ``None`` so a caller cannot confuse it
#: with a variant named ``null`` in a capture.
UNALLOCATED = object()


def bucket_for(flag_key, salt, user_key):
    """4.1: sha256 over "<flag>:<salt>:<user>", reduced to [0, 10000).

    The reduction is pinned by docs/fixtures/bucketing.csv: the first eight hex
    characters of the digest, modulo 10000. Every row of that fixture is
    reproduced by this function; no other reduction reproduces more than one of
    the twenty-four rows.

    4.2: the flag key and salt are both in the hashed string, so one user does
    not land in the same bucket for every flag.
    """
    material = "{}:{}:{}".format(flag_key, salt, user_key)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return int(digest[:DIGEST_CHARS], 16) % BUCKETS


def select_variant(rollout, bucket):
    """4.3: running totals, first one strictly above the bucket wins.

    Weights may sum to less than 10000 (spec section 1: a capture taken during
    a ramp is only part-allocated). A bucket at or above the total is not a
    rollout result at all - INC-4530 - so ``UNALLOCATED`` is returned and the
    caller carries on with the remaining rules. v2 clamped to the last entry
    here; that was the bug the incident was raised for.
    """
    running = 0
    for entry in rollout:
        running += entry["weight"]
        if bucket < running:
            return entry["variant"]
    return UNALLOCATED
