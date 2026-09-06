# Webhook relay specification

This document specifies the relay that sits between our partners and our
internal subscribers. The replay tool must reproduce its behaviour exactly.

## 1. Clock

Time is an integer millisecond counter. Every record carries the reading
taken when the relay handled it.

## 2. Signature verification

Every inbound webhook carries a signature header shaped like

    t=1712000000000,v1=<hex>,v1=<hex>

**2.1** The header is a comma-separated list of `name=value` pairs. There is
exactly one `t`. There may be one or more `v1` values. Order is not significant
and unknown names are ignored.

**2.2** The signed string is the timestamp from the header, a single `.`, then
the request body **exactly as received**. The body is never reformatted,
re-serialised or re-encoded before signing.

**2.3** A candidate signature is `HMAC-SHA256(secret, signed_string)` rendered
as lower-case hex. The header matches if **any** `v1` value equals the candidate
for **any** configured secret that is still valid. Several secrets are
configured at once so that keys can be rotated without downtime; a key may
additionally carry a retirement instant, after which it no longer signs anything
valid.

**2.4** A header with no `t`, no `v1`, a malformed pair, or a `t` that is not an
integer, fails verification with reason `MALFORMED_SIGNATURE`.

**2.5** If no `v1` matches any secret, the webhook is rejected with reason
`BAD_SIGNATURE`.

## 3. Replay window

**3.1** A webhook is stale when the gap between the clock and its header
timestamp exceeds `tolerance_ms`.

**3.2** Staleness is checked **after** the signature, so a webhook that is both
unsigned and stale is reported as a signature failure.

**3.3** A stale webhook is rejected with reason `STALE_TIMESTAMP`.

## 4. Duplicate suppression

**4.1** An accepted webhook's `event_id` is remembered with the time it was
accepted.

**4.2** A later webhook whose `event_id` was accepted within the last
`dedup_window_ms` is rejected with reason `DUPLICATE` and is not fanned out.

**4.3** Only accepted webhooks are remembered. A webhook rejected for any reason
does not suppress a later one with the same id.

**4.4** Duplicate suppression is checked after both the signature and the replay
window.

## 5. Subscriptions

**5.1** A subscriber has an id, a list of event patterns, and an enabled flag.

**5.2** A pattern is either an exact event type, or a prefix followed by `.*`.
`order.*` matches `order.created` and `order.line.added`. It does **not** match
`order`, and it does not match `orders.created`. A bare `*` matches every event
type.

**5.3** A subscriber matches an event if any of its patterns match. It receives
the event at most once however many patterns match.

**5.4** Fan-out visits subscribers in the order they were registered, not
sorted by id.

**5.5** A subscriber that is disabled at the moment of fan-out is skipped. A
subscriber registered again replaces the earlier registration and keeps its
original position in the order.

## 6. Delivery

**6.1** Each fan-out to one subscriber creates a delivery with the next delivery
id, starting at 1.

**6.2** A delivery records the subscriber id, the event id, and the attempt
number, starting at 1.

**6.3** A `200` response completes the delivery successfully.

**6.4** A `500`, `502` or `503` response schedules a retry, due after the
backoff for the attempt that just failed. `backoff_ms` lists the delays in
order.

**6.5** A `429` response schedules a retry due at `now + retry_after_ms` from the
response, ignoring `backoff_ms`.

**6.6** A `400`, `404` or `410` response dead-letters the delivery immediately
with reason `PERMANENT`.

**6.7** `max_attempts` bounds how many times a delivery may be attempted. A
delivery with no attempts left is dead-lettered with reason `EXHAUSTED` instead
of being retried.

**6.8** A response naming a delivery that is not awaiting one is ignored.

## 7. Retry dispatch

**7.1** After every record, every scheduled retry that has come due is
dispatched.

**7.2** A dispatched retry increments the delivery's attempt number and awaits a
new response.

**7.3** A retry is dispatched even if its subscriber has since been disabled.

## 8. End of session

`end` stops processing. Retries still scheduled and deliveries still awaiting a
response stay where they are; nothing is flushed.
