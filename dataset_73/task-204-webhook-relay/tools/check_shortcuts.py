#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out session catches it.

Note on what is deliberately absent: mutating the signature scheme itself -
signing the body without the timestamp, or joining them with a different
separator - is not listed. A wrong scheme cannot verify a correctly signed
payload, so the visible samples reject it immediately and it is no evidence
that the held-out corpus is doing any work.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_relay as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "sessions"


# ------------------------------------------------------ verification variants
def m_first_v1_only(R):
    class M(R):
        def op_webhook(self, rec):
            parsed = ref.parse_signature(rec.get("signature"))
            if parsed is not None:
                stamp, offered = parsed
                rec = dict(rec, signature="t=%d,v1=%s" % (stamp, offered[0]))
            return super().op_webhook(rec)
    return M


def m_first_secret_only(R):
    class M(R):
        def __init__(self, config):
            super().__init__(config)
            first = sorted(self.secrets)[0]
            self.secrets = {first: self.secrets[first]}
    return M


def m_malformed_is_bad(R):
    class M(R):
        def op_webhook(self, rec):
            before = len(self.rejected)
            super().op_webhook(rec)
            if len(self.rejected) > before and \
                    self.rejected[-1]["reason"] == "MALFORMED_SIGNATURE":
                self.rejected[-1]["reason"] = "BAD_SIGNATURE"
    return M


def m_stale_before_signature(R):
    class M(R):
        def op_webhook(self, rec):
            self.now = rec["t"]
            parsed = ref.parse_signature(rec.get("signature"))
            if parsed is not None and abs(self.now - parsed[0]) > self.tolerance:
                self.rejected.append({"event_id": rec["event_id"],
                                      "reason": "STALE_TIMESTAMP"})
                return
            super().op_webhook(rec)
    return M


def m_tolerance_exclusive(R):
    class M(R):
        def op_webhook(self, rec):
            parsed = ref.parse_signature(rec.get("signature"))
            if parsed is not None and abs(rec["t"] - parsed[0]) >= self.tolerance \
                    and ref.signature_matches(self.secrets, parsed[0], rec["body"], parsed[1]):
                self.now = rec["t"]
                self.rejected.append({"event_id": rec["event_id"],
                                      "reason": "STALE_TIMESTAMP"})
                return
            super().op_webhook(rec)
    return M


def m_tolerance_past_only(R):
    class M(R):
        def op_webhook(self, rec):
            parsed = ref.parse_signature(rec.get("signature"))
            if parsed is not None and ref.signature_matches(
                    self.secrets, parsed[0], rec["body"], parsed[1]):
                self.now = rec["t"]
                if self.now - parsed[0] > self.tolerance:   # no abs()
                    self.rejected.append({"event_id": rec["event_id"],
                                          "reason": "STALE_TIMESTAMP"})
                    return
                first = self.seen.get(rec["event_id"])
                if first is not None and self.now - first <= self.dedup_window:
                    self.rejected.append({"event_id": rec["event_id"],
                                          "reason": "DUPLICATE"})
                    return
                self.seen[rec["event_id"]] = self.now
                self.accepted.append(rec["event_id"])
                self._fan_out(rec["event_id"], rec["event_type"])
                return
            super().op_webhook(rec)
    return M


# ------------------------------------------------------------ dedup variants
def _accept_with(dedup_test=None, remember_rejected=False, refresh=False):
    def make(R):
        class M(R):
            def op_webhook(self, rec):
                self.now = rec["t"]
                event_id = rec["event_id"]
                parsed = ref.parse_signature(rec.get("signature"))
                if parsed is None:
                    self.rejected.append({"event_id": event_id,
                                          "reason": "MALFORMED_SIGNATURE"})
                    if remember_rejected:
                        self.seen[event_id] = self.now
                    return
                stamp, offered = parsed
                if not ref.signature_matches(self.secrets, stamp, rec["body"], offered):
                    self.rejected.append({"event_id": event_id, "reason": "BAD_SIGNATURE"})
                    if remember_rejected:
                        self.seen[event_id] = self.now
                    return
                if abs(self.now - stamp) > self.tolerance:
                    self.rejected.append({"event_id": event_id, "reason": "STALE_TIMESTAMP"})
                    if remember_rejected:
                        self.seen[event_id] = self.now
                    return
                first = self.seen.get(event_id)
                test = dedup_test or (lambda gap, window: gap <= window)
                if first is not None and test(self.now - first, self.dedup_window):
                    self.rejected.append({"event_id": event_id, "reason": "DUPLICATE"})
                    if refresh:
                        self.seen[event_id] = self.now
                    return
                self.seen[event_id] = self.now
                self.accepted.append(event_id)
                self._fan_out(event_id, rec["event_type"])
        return M
    return make


# ---------------------------------------------------------- matching variants
def _match_with(matcher):
    def make(R):
        class M(R):
            def _fan_out(self, event_id, event_type):
                for sub_id in self.order:
                    sub = self.subscribers[sub_id]
                    if not sub["enabled"]:
                        continue
                    if not any(matcher(p, event_type) for p in sub["events"]):
                        continue
                    did = self.next_delivery
                    self.next_delivery += 1
                    self.awaiting[did] = {"subscriber": sub_id,
                                          "event_id": event_id, "attempt": 1}
                    self._dispatch(did)
        return M
    return make


def _match_bare_prefix(pattern, event_type):
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return event_type.startswith(pattern[:-2])      # loses the dot
    return pattern == event_type


def _match_prefix_or_equal(pattern, event_type):
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        stem = pattern[:-2]
        return event_type == stem or event_type.startswith(stem + ".")
    return pattern == event_type


def m_once_per_pattern(R):
    class M(R):
        def _fan_out(self, event_id, event_type):
            for sub_id in self.order:
                sub = self.subscribers[sub_id]
                if not sub["enabled"]:
                    continue
                for pattern in sub["events"]:
                    if not ref.pattern_matches(pattern, event_type):
                        continue
                    did = self.next_delivery
                    self.next_delivery += 1
                    self.awaiting[did] = {"subscriber": sub_id,
                                          "event_id": event_id, "attempt": 1}
                    self._dispatch(did)
    return M


def m_fanout_sorted_by_id(R):
    class M(R):
        def _fan_out(self, event_id, event_type):
            saved = self.order
            self.order = sorted(self.order)
            try:
                super()._fan_out(event_id, event_type)
            finally:
                self.order = saved
    return M


def m_resubscribe_moves_to_end(R):
    class M(R):
        def op_subscribe(self, rec):
            self.now = rec["t"]
            if rec["id"] in self.order:
                self.order.remove(rec["id"])
            self.order.append(rec["id"])
            self.subscribers[rec["id"]] = {"events": rec["events"],
                                           "enabled": rec["enabled"]}
    return M


def m_disabled_still_receives(R):
    class M(R):
        def _fan_out(self, event_id, event_type):
            for sub_id in self.order:
                sub = self.subscribers[sub_id]
                if not any(ref.pattern_matches(p, event_type) for p in sub["events"]):
                    continue
                did = self.next_delivery
                self.next_delivery += 1
                self.awaiting[did] = {"subscriber": sub_id,
                                      "event_id": event_id, "attempt": 1}
                self._dispatch(did)
    return M


# ------------------------------------------------------------ retry variants
def m_backoff_off_by_one(R):
    class M(R):
        def _backoff_for(self, attempt):
            index = min(attempt, len(self.backoff) - 1)      # indexes by attempt
            return self.backoff[index]
    return M


def m_backoff_first_when_over(R):
    class M(R):
        def _backoff_for(self, attempt):
            index = attempt - 1
            return self.backoff[index] if index < len(self.backoff) else self.backoff[0]
    return M


def m_due_strictly_after(R):
    class M(R):
        def pump(self):
            while True:
                ready = [item for item in self.scheduled if item[0] < self.now]
                if not ready:
                    return
                ready.sort()
                due, did = ready[0]
                self.scheduled.remove((due, did))
                self.awaiting[did]["attempt"] += 1
                self._dispatch(did)
    return M


def m_retry_after_ignored(R):
    class M(R):
        def op_response(self, rec):
            if rec["status"] == 429 and rec["delivery"] in self.awaiting:
                self.now = rec["t"]
                attempt = self.awaiting[rec["delivery"]]["attempt"]
                self._retry_or_dlq(rec["delivery"], self.now + self._backoff_for(attempt))
                return
            super().op_response(rec)
    return M


def m_max_attempts_excludes_first(R):
    class M(R):
        def _retry_or_dlq(self, delivery_id, due):
            record = self.awaiting[delivery_id]
            if record["attempt"] > self.max_attempts:        # allows one more
                self.dlq.append({"delivery": delivery_id,
                                 "subscriber": record["subscriber"],
                                 "event_id": record["event_id"],
                                 "reason": "EXHAUSTED"})
                del self.awaiting[delivery_id]
                return
            self.scheduled.append((due, delivery_id))
    return M


def m_dispatch_by_delivery_id(R):
    class M(R):
        def pump(self):
            while True:
                ready = [item for item in self.scheduled if item[0] <= self.now]
                if not ready:
                    return
                ready.sort(key=lambda item: item[1])          # id, not due time
                due, did = ready[0]
                self.scheduled.remove((due, did))
                self.awaiting[did]["attempt"] += 1
                self._dispatch(did)
    return M


def m_permanent_is_retried(R):
    class M(R):
        def op_response(self, rec):
            if rec["status"] in ref.PERMANENT_STATUSES:
                rec = dict(rec, status=503)
            super().op_response(rec)
    return M


def m_settled_delivery_reopens(R):
    class M(R):
        def op_response(self, rec):
            did = rec["delivery"]
            if did not in self.awaiting and did in set(self.completed) \
                    and rec["status"] in ref.RETRY_STATUSES:
                self.now = rec["t"]
                self.awaiting[did] = {"subscriber": "?", "event_id": "?", "attempt": 1}
                self._retry_or_dlq(did, self.now + self.backoff[0])
                return
            super().op_response(rec)
    return M


SHORTCUTS = [
    ("only the first v1 value is checked", m_first_v1_only),
    ("only one configured secret is tried", m_first_secret_only),
    ("a malformed header is reported as a bad signature", m_malformed_is_bad),
    ("staleness is checked before the signature", m_stale_before_signature),
    ("the replay window boundary is exclusive", m_tolerance_exclusive),
    ("only past timestamps count as stale", m_tolerance_past_only),
    ("the dedup window boundary is exclusive", _accept_with(lambda gap, w: gap < w)),
    ("a suppressed duplicate refreshes the window", _accept_with(refresh=True)),
    ("a rejected webhook still suppresses later ones", _accept_with(remember_rejected=True)),
    ("order.* matches orders.created", _match_with(_match_bare_prefix)),
    ("order.* matches order itself", _match_with(_match_prefix_or_equal)),
    ("a subscriber is delivered once per matching pattern", m_once_per_pattern),
    ("fan-out visits subscribers in id order", m_fanout_sorted_by_id),
    ("re-registering moves a subscriber to the end", m_resubscribe_moves_to_end),
    ("a disabled subscriber still receives events", m_disabled_still_receives),
    ("the backoff table is indexed by attempt number", m_backoff_off_by_one),
    ("the backoff table restarts instead of repeating its last entry", m_backoff_first_when_over),
    ("a retry is due strictly after its due time", m_due_strictly_after),
    ("Retry-After is ignored in favour of the backoff table", m_retry_after_ignored),
    ("max_attempts counts only the retries", m_max_attempts_excludes_first),
    ("due retries are dispatched in delivery id order", m_dispatch_by_delivery_id),
    ("a permanent failure is retried", m_permanent_is_retried),
    ("a response can reopen a completed delivery", m_settled_delivery_reopens),
]


def run(cls, text):
    config, records = ref.parse_session(text)
    relay = cls(config)
    for rec in records:
        if rec["op"] == "end":
            break
        getattr(relay, ref.HANDLERS[rec["op"]])(rec)
        relay.pump()
    return relay.report()


def main():
    sample_files = sorted(SAMPLES.glob("*.session"))
    held_files = sorted(HELD_OUT.glob("*.session"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.replay_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.replay_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, make in SHORTCUTS:
        cls = make(ref.Relay)
        ok = True
        for f in sample_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out session:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
