# Backfill runner v1 - implementation notes

> **Superseded by `docs/backfill-spec.md`.** Kept for the incident archive.
> These notes describe the v1 runner and capture format 1. Do not implement
> from them.

## What v1 did

v1 walked the range in fixed chunks and reported progress from the loop
counter. It was deliberately simple; the complications came later.

### Progress accounting

The checkpoint was advanced as each chunk was **dispatched**, not when it
committed. The reasoning at the time was that a chunk that had been sent had
been sent, and the retry would fix any shortfall:

    checkpoint += chunk_size          # after every attempt

It kept the accounting to one line and it made the progress bar move, which
is what people were asking for. INC-2291 is the counter-argument.

### Percentage

v1 reported `round(100 * done / total)`, so a job 995 keys into 1000 showed
100%. Operators liked it: a job that is 99.5% done is done as far as the
morning stand-up is concerned.

### Rate limiting

v1 held its own token bucket in-process and refilled it on a timer, so a
restart handed the job a full bucket. This was the source of the thundering
herd every deploy. The limiter moved out to the gateway in v2.

### Timestamps

v1 stamped `t` as seconds since the epoch, so a capture had one clock and one
timeline and could be read straight through. v2 stamps process-relative
seconds instead - see `docs/session-format.md` - which is the change most
people trip over when they open an old script on a new capture.

### Chunk sizing

v1 read `chunk_size` from config at startup and never looked again; there was
no control table and nothing could be retuned without a redeploy.

## Why any of this is still here

INC-2291, INC-3902 and INC-4110 all have v1 captures attached, and the
post-incident reviews cite line numbers in this file.
