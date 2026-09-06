#!/usr/bin/env python3
"""limiter_doctor - replay a decision capture and explain every deny.

    python3 tools/limiter_doctor.py capture/trace-02-policy-rollout.jsonl

UNSUPPORTED. Written during INC-8812 (see docs/incident-8812.md) against
gateway 3.9 and never updated. It is kept in the tree because on-call still
uses the deny summary at the bottom; the token reconstruction has been wrong
on some traces since at least 4.0 and nobody has had time to work out why.
Trust `tokens_after` in the capture over the `recon` column here.

  -- edge-platform, 2026-01-12
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_policies(ref):
    """Load the `policies` array of a control-plane export."""
    path = ref if os.path.isabs(ref) else os.path.join(ROOT, ref)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)["policies"]


def tenant_of(key):
    head, sep, _rest = key.partition(":")
    return head if sep else None


class Policy(object):
    def __init__(self, capacity, rate):
        self.capacity = float(capacity)
        self.rate = float(rate)


class PolicyBook(object):
    """Current settings per tenant.

    The control plane publishes in revision order, so the newest revision for a
    tenant is that tenant's current policy. That is the whole rule.
    """

    def __init__(self, rows, default_capacity, default_rate):
        self.current = {"*": Policy(default_capacity, default_rate)}
        best = {}
        for row in rows or ():
            tenant = row.get("tenant", "*")
            revision = row.get("revision", 0)
            if tenant not in best or revision > best[tenant]:
                best[tenant] = revision
                self.current[tenant] = Policy(row["capacity"], row["rate"])

    def for_key(self, key):
        tenant = tenant_of(key)
        if tenant is not None and tenant in self.current:
            return self.current[tenant]
        return self.current["*"]


class Bucket(object):
    def __init__(self, policy, now):
        self.tokens = policy.capacity
        self.last_update = now

    def refill(self, policy, now):
        elapsed = max(0.0, now - self.last_update)
        self.last_update = now
        self.tokens = min(policy.capacity, self.tokens + elapsed * policy.rate)

    def take(self, policy, cost, now):
        self.refill(policy, now)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class Windows(object):
    def __init__(self):
        self.timelines = {}

    def call(self, key, now, window_sec, max_reqs):
        timeline = self.timelines.setdefault(key, [])
        cutoff = now - window_sec
        # Arrivals go on the end in time order, so everything that has expired
        # is at the front: peel it off and stop at the first live entry.
        while timeline and timeline[0] < cutoff:
            timeline.pop(0)
        if len(timeline) < max_reqs:
            timeline.append(now)
            return True
        return False


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: limiter_doctor.py <capture.jsonl>\n")
        return 2
    path = argv[1] if os.path.isabs(argv[1]) else os.path.join(ROOT, argv[1])
    with open(path, "r", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]

    header = records[0]
    config = header.get("config", {})
    rows = config.get("policies")
    if isinstance(rows, str):
        rows = load_policies(rows)
    book = PolicyBook(rows, config.get("capacity", 10), config.get("rate", 1.0))

    buckets = {}
    windows = Windows()
    denies = []
    mismatches = 0

    print("trace %s (gateway %s)"
          % (header.get("trace"), header.get("gateway_version")))
    print("%-14s %-22s %6s %6s %8s %8s"
          % ("t", "key", "cost", "dec", "recon", "recorded"))

    for record in records[1:]:
        op = record.get("op")
        now = float(record["t"])
        key = record["key"]

        if op == "window":
            decision = windows.call(key, now, record["window_sec"],
                                    record["max_reqs"])
            flag = "" if decision == record["decision"] else "  <-- MISMATCH"
            if decision != record["decision"]:
                mismatches += 1
            print("%-14.6f %-22s %6s %6s %8s %8s%s"
                  % (now, key, "-", str(decision)[0], "-",
                     str(record["decision"])[0], flag))
            if not record["decision"]:
                denies.append((now, key, "window full, lower the call rate or "
                                         "raise max_reqs"))
            continue

        policy = book.for_key(key)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = buckets[key] = Bucket(policy, now)

        if op == "allow":
            decision = bucket.take(policy, record["cost"], now)
            recon = bucket.tokens
            ok = (decision == record["decision"]
                  and abs(recon - record["tokens_after"]) < 1e-6)
            if not ok:
                mismatches += 1
            print("%-14.6f %-22s %6s %6s %8.4f %8.4f%s"
                  % (now, key, record["cost"], str(decision)[0], recon,
                     record["tokens_after"], "" if ok else "  <-- MISMATCH"))
            if not record["decision"]:
                denies.append((now, key,
                               "bucket exhausted (recon %.2f tokens, cost %s), "
                               "raise rate or capacity"
                               % (recon, record["cost"])))
        else:
            bucket.refill(policy, now)
            recon = bucket.tokens
            ok = abs(recon - record["tokens_after"]) < 1e-6
            if not ok:
                mismatches += 1
            print("%-14.6f %-22s %6s %6s %8.4f %8.4f%s"
                  % (now, key, "-", "-", recon, record["tokens_after"],
                     "" if ok else "  <-- MISMATCH"))

    print("")
    print("diagnoses")
    for now, key, text in denies:
        print("  %s deny at t=%.6f: %s" % (key, now, text))
    print("")
    print("%d line(s) where the reconstruction did not match the capture."
          % mismatches)
    if mismatches:
        print("(known issue, see the module docstring; the capture is the "
              "source of truth)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
