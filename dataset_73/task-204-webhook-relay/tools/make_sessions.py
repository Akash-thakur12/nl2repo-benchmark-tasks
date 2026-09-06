#!/usr/bin/env python3
"""Regenerate the sample and held-out session corpora, and samples/expected.json.

  samples/          Six sessions from a partner and a fleet that both behave:
                    one configured secret, one v1 signature per request, the
                    header timestamp equal to the arrival time, exact event
                    patterns with no wildcards, every subscriber enabled and
                    registered in id order, no repeats and every delivery
                    answered 200 first time. Almost every plausible reading of
                    the specification reproduces expected.json here.

  audit/            An extract from the live relay's own audit log, exported
                    in the report's own shape. This is the evidence the
                    specification no longer spells out: the tolerance and dedup
                    boundaries, the backoff index origin and its repeating last
                    entry, the attempt budget, the due-time boundary and
                    dispatch order, the monotone clock, and which clock a key's
                    retirement instant is judged against.

  tests/sessions/   Held-out sessions covering the rest: malformed headers, key
                    rotation and retirement, several v1 values, the replay
                    window boundary, duplicate suppression and its window, the
                    monotone clock, wildcard matching, registration order,
                    disabled subscribers, retry scheduling and backoff,
                    Retry-After, exhaustion and permanent failures.

This script does not ship in the task image.
"""
import hashlib
import hmac
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_relay  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
AUDIT = ROOT / "environment" / "audit"
HELD_OUT = ROOT / "tests" / "sessions"

K1 = "sk_live_primary"
K2 = "sk_live_rotated"

ONE_SECRET = {"k1": K1}
TWO_SECRETS = {"k1": K1, "k2": K2}


def sign(secret, timestamp, body):
    signed = "%d.%s" % (timestamp, body)
    return hmac.new(secret.encode("utf-8"), signed.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def config(secrets=None, tolerance_ms=300000, dedup_window_ms=600000,
           max_attempts=3, backoff_ms=None, retired=None):
    record = {"op": "config", "tolerance_ms": tolerance_ms,
              "dedup_window_ms": dedup_window_ms, "max_attempts": max_attempts,
              "backoff_ms": backoff_ms or [1000, 5000],
              "secrets": secrets or ONE_SECRET}
    if retired is not None:
        record["retired"] = retired
    return record


def sub(t, sub_id, events, enabled=True):
    return {"op": "subscribe", "t": t, "id": sub_id, "events": events,
            "enabled": enabled}


def hook(t, event_id, event_type, body="{}", secret=K1, stamp=None, header=None):
    stamp = t if stamp is None else stamp
    if header is None:
        header = "t=%d,v1=%s" % (stamp, sign(secret, stamp, body))
    return {"op": "webhook", "t": t, "event_id": event_id,
            "event_type": event_type, "body": body, "signature": header}


def resp(t, delivery, status, retry_after_ms=None):
    record = {"op": "response", "t": t, "delivery": delivery, "status": status}
    if retry_after_ms is not None:
        record["retry_after_ms"] = retry_after_ms
    return record


def tick(t):
    return {"op": "tick", "t": t}


def end(t):
    return {"op": "end", "t": t}


# ------------------------------------------------------------ benign samples
def benign():
    s = {}

    s["s01"] = [config(),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "evt_1", "order.created"),
                resp(1100, 1, 200),
                end(2000)]

    s["s02"] = [config(),
                sub(10, "alpha", ["order.created"]),
                sub(20, "beta", ["order.created"]),
                hook(1000, "evt_1", "order.created"),
                resp(1100, 1, 200),
                resp(1200, 2, 200),
                end(2000)]

    s["s03"] = [config(),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "evt_1", "order.created"),
                resp(1100, 1, 200),
                hook(2000, "evt_2", "order.created"),
                resp(2100, 2, 200),
                end(3000)]

    s["s04"] = [config(),
                sub(10, "alpha", ["order.created"]),
                sub(20, "beta", ["invoice.paid"]),
                hook(1000, "evt_1", "invoice.paid"),
                resp(1100, 1, 200),
                end(2000)]

    s["s05"] = [config(),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "evt_1", "shipment.created"),
                end(2000)]

    s["s06"] = [config(),
                sub(10, "alpha", ["order.created", "invoice.paid"]),
                hook(1000, "evt_1", "order.created", body='{"id":1}'),
                resp(1100, 1, 200),
                hook(2000, "evt_2", "invoice.paid", body='{"id":2}'),
                resp(2100, 2, 200),
                end(3000)]
    return s


# ------------------------------------------------------- audit log extract
def audit():
    """A slice of the live relay's own audit log. Ships inside environment/ and
    is the recoverable ground truth for every rule the specification states in
    prose without pinning: each session below is chosen so that exactly one
    reading reproduces it."""
    s = {}
    zeros = "0" * 64

    # a01: the clock is a high-water reading, and the replay window boundary.
    #   evt_b arrives carrying an earlier reading than the record before it: it
    #         is accepted, but the attempt it produces is stamped with the
    #         high-water reading, not with its own t.
    #   evt_c arrives earlier still and is STALE against the high-water clock -
    #         no reading in which the clock rewinds produces that rejection.
    #   evt_d is exactly tolerance_ms away and is accepted; evt_e is one
    #         millisecond further and is not. evt_f/evt_g do the same in the
    #         future direction.
    s["a01"] = [config(tolerance_ms=1000),
                sub(10, "alpha", ["order.created"]),
                hook(5000, "evt_a", "order.created"),
                resp(5200, 1, 200),
                hook(4400, "evt_b", "order.created", stamp=4400),
                resp(5300, 2, 200),
                hook(4000, "evt_c", "order.created", stamp=4000),
                hook(6300, "evt_d", "order.created", stamp=5300),
                resp(6400, 3, 200),
                hook(6400, "evt_e", "order.created", stamp=5399),
                hook(6500, "evt_f", "order.created", stamp=7501),
                hook(6600, "evt_g", "order.created", stamp=7600),
                resp(6700, 4, 200),
                end(7000)]

    # a02: the duplicate window. evt_h repeats at exactly dedup_window_ms (still
    # a duplicate) and again one millisecond past it. The second repeat is only
    # accepted if the suppressed one left the first acceptance time alone.
    # The trailing evt_i also arrives out of order and is stamped high-water.
    s["a02"] = [config(dedup_window_ms=1000, tolerance_ms=100000),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "evt_h", "order.created"),
                resp(1050, 1, 200),
                hook(2000, "evt_h", "order.created"),
                hook(2001, "evt_h", "order.created"),
                resp(2100, 2, 200),
                hook(3100, "evt_h", "order.created"),
                resp(3150, 3, 200),
                tick(3200),
                hook(2500, "evt_i", "order.created", stamp=2500),
                end(9000)]

    # a03: key retirement. k1 was withdrawn at 5000.
    #   evt_j  signed exactly at 5000, handled at 5400  -> accepted
    #   evt_k  signed at 5001, one millisecond past it  -> BAD_SIGNATURE
    #   evt_l  signed at 4900 with the successor key    -> accepted
    #   evt_n  signed at 4000 with k1, handled at 6100  -> accepted
    s["a03"] = [config(secrets=TWO_SECRETS, retired={"k1": 5000},
                       tolerance_ms=100000),
                sub(10, "alpha", ["order.created"]),
                hook(5400, "evt_j", "order.created", secret=K1, stamp=5000),
                resp(5500, 1, 200),
                hook(5001, "evt_k", "order.created", secret=K1, stamp=5001),
                hook(5700, "evt_l", "order.created", secret=K2, stamp=4900),
                resp(5800, 2, 200),
                hook(5900, "evt_m", "order.created", secret=K2, stamp=5900),
                resp(6000, 3, 200),
                hook(6100, "evt_n", "order.created", secret=K1, stamp=4000),
                resp(6200, 4, 200),
                end(7000)]

    # a04: the backoff table and the attempt budget. Every retry is preceded by
    # a tick one millisecond short of its due time (nothing happens) and a tick
    # landing exactly on it (the retry goes out). The third failure runs past
    # the end of the table; the fourth exhausts a max_attempts of 4.
    s["a04"] = [config(max_attempts=4, backoff_ms=[1000, 5000]),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "evt_o", "order.created"),
                resp(1100, 1, 500),
                tick(2099), tick(2100),
                resp(2200, 1, 500),
                tick(7199), tick(7200),
                resp(7300, 1, 500),
                tick(12299), tick(12300),
                resp(12400, 1, 500),
                tick(20000),
                end(30000)]

    # a05: two retries come due together with their ids in the opposite order to
    # their due times, at a tick landing exactly on the later one. Then an
    # out-of-order response: the retry it schedules is measured from the
    # high-water clock, so the tick at 4900 dispatches nothing.
    s["a05"] = [config(max_attempts=4, backoff_ms=[1000], tolerance_ms=100000),
                sub(10, "alpha", ["order.created"]),
                sub(20, "beta", ["order.created"]),
                hook(1000, "evt_p", "order.created"),
                resp(1300, 2, 503),
                resp(1400, 1, 503),
                tick(2400),
                resp(2500, 1, 200),
                resp(2600, 2, 200),
                hook(3000, "evt_q", "order.created"),
                resp(3100, 3, 503),
                tick(4100),
                resp(3800, 3, 503),
                tick(4900),
                tick(5100),
                resp(5200, 3, 200),
                end(9000)]

    # a06: header parsing and the order of the admission checks.
    s["a06"] = [config(tolerance_ms=1000),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "evt_r", "order.created", header="v1=" + zeros),
                hook(1001, "evt_s", "order.created", header="t=1001"),
                hook(1002, "evt_t", "order.created", header="t=abc,v1=" + zeros),
                hook(1003, "evt_u", "order.created", header="garbage"),
                hook(1004, "evt_v", "order.created", header=""),
                hook(1005, "evt_w", "order.created", header="t=1005,v1=" + zeros),
                hook(1006, "evt_x", "order.created", header="t=1,v1=" + zeros),
                hook(1007, "evt_w", "order.created"),
                hook(1008, "evt_y", "order.created",
                     header="t=1008,v1=%s,v1=%s" % (zeros, sign(K1, 1008, "{}"))),
                hook(1009, "evt_z", "order.created",
                     header="v0=x,t=1009,v1=%s,scheme=hmac" % sign(K1, 1009, "{}")),
                resp(1100, 1, 200), resp(1101, 2, 200), resp(1102, 3, 200),
                end(2000)]

    # a07: fan-out order, wildcard reach, overlapping patterns and the disabled
    # flag. zeta is registered first and re-registered later; alpha subscribes
    # to everything; beta is disabled.
    s["a07"] = [config(),
                sub(10, "zeta", ["order.*", "order.created"]),
                sub(20, "alpha", ["*"]),
                sub(30, "beta", ["invoice.paid"], enabled=False),
                sub(40, "zeta", ["order.*", "order.created"]),
                hook(1000, "evt_aa", "order.created"),
                hook(1001, "evt_ab", "orders.created"),
                hook(1002, "evt_ac", "order"),
                hook(1003, "evt_ad", "order.line.added"),
                hook(1004, "evt_ae", "invoice.paid"),
                resp(1100, 1, 200), resp(1101, 2, 200),
                end(2000)]

    # a08: Retry-After beats the backoff table, a permanent status never
    # retries, and a response for a settled or unknown delivery is ignored.
    s["a08"] = [config(max_attempts=3, backoff_ms=[1000]),
                sub(10, "alpha", ["order.created"]),
                sub(20, "beta", ["order.created"]),
                hook(1000, "evt_af", "order.created"),
                resp(1100, 1, 429, retry_after_ms=7000),
                resp(1150, 2, 410),
                tick(2100),
                tick(8100),
                resp(8200, 1, 200),
                resp(8300, 1, 503),
                resp(8400, 99, 200),
                tick(20000),
                end(30000)]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- malformed headers (2.4) -------------------------------------------
    s["h01"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created", header="v1=deadbeef"),
                hook(1001, "e2", "order.created", header="t=1000"),
                hook(1002, "e3", "order.created", header="t=abc,v1=deadbeef"),
                hook(1003, "e4", "order.created", header="garbage"),
                hook(1004, "e5", "order.created", header=""),
                end(2000)]

    # -- a wrong signature is BAD_SIGNATURE, not malformed (2.5) -----------
    s["h02"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created", header="t=1000,v1=" + "0" * 64),
                end(2000)]

    # -- the body is signed exactly as received (2.2) ----------------------
    s["h03"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created", body='{"a": 1}'),
                {"op": "webhook", "t": 1001, "event_id": "e2",
                 "event_type": "order.created", "body": '{"a":1}',
                 "signature": "t=1001,v1=" + sign(K1, 1001, '{"a": 1}')},
                resp(1100, 1, 200),
                end(2000)]

    # -- key rotation: any configured secret may match (2.3) ---------------
    s["h04"] = [config(secrets=TWO_SECRETS), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created", secret=K1),
                hook(1001, "e2", "order.created", secret=K2),
                resp(1100, 1, 200), resp(1101, 2, 200),
                end(2000)]

    # -- several v1 values: any may match (2.3) ----------------------------
    s["h05"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created",
                     header="t=1000,v1=%s,v1=%s" % ("0" * 64, sign(K1, 1000, "{}"))),
                hook(1001, "e2", "order.created",
                     header="t=1001,v1=%s,v1=%s" % (sign(K1, 1001, "{}"), "0" * 64)),
                resp(1100, 1, 200), resp(1101, 2, 200),
                end(2000)]

    # -- unknown pairs are ignored (2.1) -----------------------------------
    s["h06"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created",
                     header="v0=x,t=1000,v1=%s,scheme=hmac" % sign(K1, 1000, "{}")),
                resp(1100, 1, 200),
                end(2000)]

    # -- the replay window is inclusive at the boundary (3.1) --------------
    s["h07"] = [config(tolerance_ms=1000), sub(10, "alpha", ["order.created"]),
                hook(5000, "e1", "order.created", stamp=4000),
                hook(5001, "e2", "order.created", stamp=6001),
                hook(5002, "e3", "order.created", stamp=3999),
                resp(5100, 1, 200),
                end(6000)]

    # -- a future timestamp counts too (3.1 uses abs) ----------------------
    s["h08"] = [config(tolerance_ms=1000), sub(10, "alpha", ["order.created"]),
                hook(5000, "e1", "order.created", stamp=7000),
                hook(5001, "e2", "order.created", stamp=6001),
                resp(5100, 1, 200),
                end(6000)]

    # -- signature is checked before staleness (3.2) -----------------------
    s["h09"] = [config(tolerance_ms=1000), sub(10, "alpha", ["order.created"]),
                hook(9000, "e1", "order.created", header="t=1,v1=" + "0" * 64),
                end(9500)]

    # -- duplicate suppression and its inclusive window (4.2, 4.4) ---------
    s["h10"] = [config(dedup_window_ms=1000), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1050, 1, 200),
                hook(1500, "e1", "order.created"),
                hook(2000, "e1", "order.created"),
                resp(2100, 2, 200),
                end(3000)]

    s["h11"] = [config(dedup_window_ms=1000, tolerance_ms=10000),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1050, 1, 200),
                hook(1900, "e1", "order.created"),
                hook(2001, "e1", "order.created"),
                resp(2100, 2, 200),
                end(3000)]

    # -- a rejected webhook does not suppress a later one (4.3) ------------
    s["h12"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created", header="t=1000,v1=" + "0" * 64),
                hook(1100, "e1", "order.created"),
                resp(1200, 1, 200),
                end(2000)]

    # -- wildcard matching (5.2) -------------------------------------------
    s["h13"] = [config(), sub(10, "alpha", ["order.*"]),
                hook(1000, "e1", "order.created"),
                hook(1001, "e2", "order.line.added"),
                hook(1002, "e3", "order"),
                hook(1003, "e4", "orders.created"),
                resp(1100, 1, 200), resp(1101, 2, 200),
                end(2000)]

    s["h14"] = [config(), sub(10, "alpha", ["*"]),
                hook(1000, "e1", "anything.at.all"),
                resp(1100, 1, 200),
                end(2000)]

    # -- overlapping patterns deliver once (5.3) ---------------------------
    s["h15"] = [config(), sub(10, "alpha", ["order.*", "order.created", "*"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 200),
                end(2000)]

    # -- fan-out follows registration order, not id order (5.4) ------------
    s["h16"] = [config(), sub(10, "zeta", ["order.created"]),
                sub(20, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 200), resp(1101, 2, 200),
                end(2000)]

    # -- re-registering keeps the original position (5.5) ------------------
    s["h17"] = [config(), sub(10, "zeta", ["order.created"]),
                sub(20, "alpha", ["order.created"]),
                sub(30, "zeta", ["order.created"]),
                hook(1000, "e1", "order.created"),
                end(2000)]

    # -- disabled subscribers are skipped at fan-out (5.5) -----------------
    s["h18"] = [config(), sub(10, "alpha", ["order.created"], enabled=False),
                sub(20, "beta", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 200),
                end(2000)]

    s["h19"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                sub(1100, "alpha", ["order.created"], enabled=False),
                hook(1200, "e2", "order.created"),
                end(2000)]

    # -- retry scheduling and backoff progression (6.4, 7.1) ---------------
    s["h20"] = [config(backoff_ms=[1000, 5000]), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 500),
                tick(2099),
                tick(2100),
                resp(2200, 1, 200),
                end(9000)]

    # -- the last backoff entry repeats (6.4) ------------------------------
    s["h21"] = [config(max_attempts=5, backoff_ms=[1000]),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 503),
                tick(2100),
                resp(2200, 1, 503),
                tick(3200),
                resp(3300, 1, 200),
                end(9000)]

    # -- a retry is due at exactly its due time (7.1 uses <=) --------------
    s["h22"] = [config(backoff_ms=[1000]), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1000, 1, 502),
                tick(1999),
                tick(2000),
                end(9000)]

    # -- Retry-After overrides the backoff table (6.5) ---------------------
    s["h23"] = [config(backoff_ms=[1000]), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 429, retry_after_ms=7000),
                tick(2200),
                tick(8100),
                end(9000)]

    # -- max_attempts counts the first delivery (6.7) ----------------------
    s["h24"] = [config(max_attempts=2, backoff_ms=[100]),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 500),
                tick(1200),
                resp(1300, 1, 500),
                end(9000)]

    s["h25"] = [config(max_attempts=1, backoff_ms=[100]),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 500),
                end(9000)]

    # -- permanent failures never retry (6.6) ------------------------------
    s["h26"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 410),
                tick(9000),
                end(9500)]

    # -- a response for an unknown or settled delivery is ignored (6.8) ----
    s["h27"] = [config(), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 99, 200),
                resp(1200, 1, 200),
                resp(1300, 1, 500),
                tick(9000),
                end(9500)]

    # -- retries are dispatched even for a since-disabled subscriber (7.3) -
    s["h28"] = [config(backoff_ms=[500]), sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 503),
                sub(1200, "alpha", ["order.created"], enabled=False),
                tick(1700),
                end(9000)]

    # -- several retries come due at once, oldest first then by id (7.1) ---
    s["h29"] = [config(backoff_ms=[1000]),
                sub(10, "alpha", ["order.created"]),
                sub(20, "beta", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 2, 503),
                resp(1200, 1, 503),
                tick(5000),
                end(9000)]

    # -- a fan-out to several subscribers with mixed outcomes --------------
    s["h30"] = [config(max_attempts=2, backoff_ms=[100]),
                sub(10, "alpha", ["order.*"]),
                sub(20, "beta", ["*"]),
                sub(30, "gamma", ["invoice.paid"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 200),
                resp(1150, 2, 400),
                hook(1200, "e2", "invoice.paid"),
                resp(1300, 3, 500),
                tick(1400),
                resp(1500, 3, 500),
                resp(1600, 4, 200),
                end(9000)]
    # -- past the end of the backoff table, the last entry repeats (6.4) ---
    s["h31"] = [config(max_attempts=4, backoff_ms=[1000, 5000]),
                sub(10, "alpha", ["order.created"]),
                hook(1000, "e1", "order.created"),
                resp(1100, 1, 500),
                tick(2100),
                resp(2200, 1, 500),
                tick(7200),
                resp(7300, 1, 500),
                tick(9000),
                tick(20000),
                end(30000)]

    # -- the clock is monotone: a backwards record does not rewind it (1) ----
    s["h32"] = [config(tolerance_ms=1000), sub(10, "alpha", ["order.created"]),
                hook(5000, "e1", "order.created"),
                resp(5200, 1, 200),
                hook(4000, "e2", "order.created", stamp=4000),
                hook(4400, "e3", "order.created", stamp=4400),
                resp(5300, 2, 200),
                end(6000)]

    # -- a backwards response does not rewind a retry's due time (1, 6.4) ----
    s["h33"] = [config(max_attempts=3, backoff_ms=[1000], tolerance_ms=100000),
                sub(10, "alpha", ["order.created"]),
                hook(3000, "e1", "order.created"),
                resp(3100, 1, 503),
                tick(4100),
                resp(3800, 1, 503),
                tick(4900),
                tick(5100),
                resp(5200, 1, 200),
                end(9000)]

    # -- attempts are stamped with the high-water reading (1, 6.2) -----------
    s["h34"] = [config(tolerance_ms=100000),
                sub(10, "alpha", ["order.*"]),
                tick(8000),
                sub(500, "beta", ["order.created"]),
                hook(2000, "e1", "order.created", stamp=2000),
                resp(8100, 1, 200),
                resp(8200, 2, 200),
                tick(7000),
                hook(8300, "e2", "order.created"),
                end(9000)]

    # -- a retired key still verifies what it signed before it went (2.3) ----
    s["h35"] = [config(secrets=TWO_SECRETS, retired={"k1": 5000},
                       tolerance_ms=100000),
                sub(10, "alpha", ["order.created"]),
                hook(5400, "e1", "order.created", secret=K1, stamp=5000),
                resp(5500, 1, 200),
                hook(5600, "e2", "order.created", secret=K1, stamp=5001),
                hook(5700, "e3", "order.created", secret=K1, stamp=4999),
                resp(5800, 2, 200),
                end(9000)]

    # -- every key carries its own retirement instant (2.3) ------------------
    s["h36"] = [config(secrets=TWO_SECRETS, retired={"k1": 3000, "k2": 9000},
                       tolerance_ms=100000),
                sub(10, "alpha", ["order.created"]),
                hook(4000, "e1", "order.created", secret=K2, stamp=4000),
                resp(4100, 1, 200),
                hook(4200, "e2", "order.created", secret=K1, stamp=3000),
                resp(4300, 2, 200),
                hook(4400, "e3", "order.created", secret=K1, stamp=3001),
                hook(9500, "e4", "order.created", secret=K2, stamp=9001),
                hook(9600, "e5", "order.created", secret=K2, stamp=9000),
                resp(9700, 3, 200),
                end(10000)]

    return s


def write(target, sessions):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(sessions.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".session")).write_text(text, encoding="utf-8", newline="\n")


def expected_for(target, sessions):
    expected = {}
    for name in sorted(sessions):
        text = (target / (name + ".session")).read_text(encoding="utf-8")
        expected[name] = reference_relay.replay_text(text)
    (target / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")


def main():
    samples = benign()
    audit_sessions = audit()
    write(SAMPLES, samples)
    write(AUDIT, audit_sessions)
    write(HELD_OUT, held_out())

    expected_for(SAMPLES, samples)
    expected_for(AUDIT, audit_sessions)

    print("samples  : %d" % len(samples))
    print("audit    : %d" % len(audit_sessions))
    print("held-out : %d" % len(held_out()))
    print("expected.json written for samples and audit")


if __name__ == "__main__":
    main()
