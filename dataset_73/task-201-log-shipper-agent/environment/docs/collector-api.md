# Collector ingest API

The contract between a shipper and the collector it forwards to. The shipper is
written against this document; the replay tool has to reproduce the shipper, so
where `shipper-spec.md` defers to this file, this file is normative.

## 1. Requests

A shipper submits one **request** per batch. A request carries an ordered list
of **records**; each record is one log line, with its terminating newline
stripped by the shipper before submission.

The collector answers every request exactly once, with one of the statuses
listed in section 5 of `shipper-spec.md`.

## 2. Request limits

A request is accepted only if it is within both of the following limits, which
are the shipper's `max_lines` and `max_bytes`:

**2.1** a request carries **at most `max_lines` records**;

**2.2** a request carries **at most `max_bytes` of payload**, where the payload
size of a request is the sum, over its records, of the record's length in UTF-8
bytes plus one framing byte per record. (That framing byte is the newline the
shipper stripped; the collector re-adds it. It is the same accounting as
`shipper-spec.md` 4.2 and 6.1, so a batch is measured exactly as the buffer that
produced it was measured.)

**2.3** A request that breaches either limit is rejected with `413` and no
records from it are ingested. Shippers therefore assemble a request by walking
their buffer from the front and stopping before the first record that would push
the request past either limit.

**2.4** The one exception: a **single record larger than `max_bytes` is
accepted**, provided it is the only record in the request. A shipper must not
withhold an oversize line; it sends it on its own. This is why every request
carries at least one record.

## 3. Retry budget

The number of times a request may be re-submitted after a transient failure -
the shipper's `max_retries` - is **negotiated per request, at submission**, and
travels with that request.

**3.1** Reconfiguring a shipper does not change the budget of a request that is
already in flight. A request submitted under one budget is judged against that
budget when its response arrives, however long it takes and whatever the shipper
has been reconfigured to since.

**3.2** A request assembled after a reconfiguration is submitted under, and
judged against, the new budget.

This is what `shipper-spec.md` 5.3 compares an attempt count against.

## 4. Batch identifiers

The shipper chooses the identifier; the collector echoes it back in the
response. The collector does not require identifiers to arrive in order, and it
does not require the shipper to wait for one response before submitting the next
request.
