# Log shipper behaviour specification

This document specifies the shipper we run on every application host. The replay
tool must reproduce its behaviour exactly.

The shipper tails append-only log files, groups complete lines into batches,
sends batches to a collector, and tracks which bytes have been durably accepted.

## 1. Clock

Time is an integer millisecond counter. It only changes when the session says it
does. Every event carries the time at which it happens.

## 2. Reading

Each file is a byte stream that only grows, except when it is rotated. The
shipper keeps, per file:

- `read_offset` - how many bytes it has consumed
- `acked_offset` - how many bytes the collector has durably accepted

**2.1** A line is only consumed once its terminating `\n` has been appended. A
trailing fragment with no newline stays in the file and is not consumed.

**2.2** Consumed lines are held in the pending buffer in read order, without the
terminating newline. Each pending line records the file offset just past its
newline, and the time at which it was consumed.

**2.3** Reading happens as part of an `append` event, and only then.

## 3. Rotation

**3.1** On rotation the file is replaced by a new, empty stream. `read_offset`
and `acked_offset` for that file both reset to 0.

**3.2** An unterminated fragment at the end of the rotated-away stream is lost.
It is never shipped.

**3.3** Lines already in the pending buffer survive rotation and are still
shipped. Their recorded offsets refer to the stream they came from, which no
longer exists, so acking them cannot move the new stream's `acked_offset`.

## 4. Batching

A flush is attempted after every event. The pending buffer is flushed when any
of these holds:

**4.1** the buffer holds at least `max_lines` lines, or
**4.2** the buffer holds at least `max_bytes` bytes, counting each line's bytes
plus one byte per line for the newline that was stripped, or
**4.3** the oldest pending line was consumed at least `max_age_ms` ago,
measured against the current time.

Any one of the three is sufficient. They are checked in the order 4.1, 4.2, 4.3
but the outcome does not depend on the order.

**4.4** A flush takes **up to `max_lines` lines** from the front of the buffer -
never more, even if the buffer is longer. If the buffer still satisfies a flush
condition afterwards, it flushes again, in the same event.

**4.5** Each flush creates a batch with the next batch id, starting at 1 and
increasing by one for every batch ever created. Ids are never reused. Lines that
are requeued and flushed again form a **new** batch with a **new** id.

**4.6** A batch that has been created and not yet resolved is *in flight*. There
is no limit on how many batches may be in flight.

## 5. Collector responses

A `response` event names a batch id and a status.

**5.1** `200` - the batch is accepted. It is appended to the delivered list in
the order the responses arrive, not in batch id order. For each line in the
batch, that line's file `acked_offset` becomes the maximum of its current value
and the line's recorded offset.

**5.2** `500`, `502`, `503` - the batch failed transiently. Every line in the
batch has its own attempt count increased by one. A line's attempt count is 1
while it is in its first batch.

**5.3** A line whose attempt count is now greater than `max_retries` goes to the
dead-letter list, in order. Every other line in the batch is put back at the
**front** of the pending buffer, in its original order, ahead of anything that
arrived while the batch was in flight.

**5.4** `400`, `413`, `422` - the batch is rejected permanently. Its lines go
straight to the dead-letter list in order, regardless of attempt count.

**5.5** A response naming a batch id that is not in flight is ignored.

## 6. Backpressure

**6.1** The pending buffer may hold at most `spool_max_bytes`, measured the same
way as 4.2.

**6.2** When adding lines would exceed that limit, lines are dropped from the
**front** of the buffer - the oldest - until the buffer fits. Dropped lines are
counted in `dropped` and are not sent anywhere, not even the dead-letter list.

**6.3** The limit is applied after lines are added, including lines requeued by
5.2, and a requeued line may itself be dropped.

## 7. Restart

**7.1** A `restart` event clears the pending buffer and forgets every in-flight
batch. Batch ids continue from where they were; ids are never reused.

**7.2** For each file, `read_offset` returns to `acked_offset`, so any bytes
accepted but not yet acked are read again. This is an at-least-once shipper and
duplicate delivery after a restart is correct behaviour.

**7.3** A response for a batch that was in flight at restart is ignored, per 5.5.

## 8. End of session

**8.1** `end` stops processing. There is no final flush: whatever is still
pending stays pending.

**8.2** The report is then produced from the state as it stands.

## 9. Configuration

The first record of a session is a `config` record carrying `max_lines`,
`max_bytes`, `max_age_ms`, `max_retries` and `spool_max_bytes`. All are positive
integers.
