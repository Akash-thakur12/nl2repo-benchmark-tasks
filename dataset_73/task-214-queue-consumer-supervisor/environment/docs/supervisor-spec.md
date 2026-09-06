# Supervisor specification

This document specifies how the supervisor keeps queue workers alive. The
replay tool must reproduce it exactly.

## 1. Clock and workers

**1.1** Time is an integer millisecond counter that moves only when a record
says so. Records are in non-decreasing time order, so time never goes backwards.

**1.2** Every configured worker starts `running` at time 0, with its last
heartbeat at 0, no restarts recorded and no work in hand.

**1.3** A record naming a worker the configuration does not list produces the
error `UNKNOWN_WORKER` naming it, and is otherwise ignored.

## 2. Health

**2.1** A running worker is unhealthy when `now - last_heartbeat` is **strictly
greater** than `heartbeat_timeout_ms`. Exactly at the timeout it is still
healthy.

**2.2** Health is evaluated after every record, for every running worker, in
configuration order.

**2.3** An unhealthy worker is treated exactly as though it had crashed at that
moment, and records a `crashed` event.

**2.4** A heartbeat from a worker that is not running is ignored, and is not an
error.

## 3. Crashes and restarts

**3.1** A crash stops the worker and records a `crashed` event. The worker is
then `down`.

**3.2** A crash appends the current time to the worker's restart history.

**3.3** If the number of entries in that history within the last
`restart_window_ms` is greater than `max_restarts`, the worker becomes `failed`
and records a `failed` event. A failed worker is never restarted and never
evaluated again.

**3.4** Otherwise a restart is scheduled for `now + backoff`, where `backoff` is
`backoff_ms[attempt]`, `attempt` being how many consecutive restarts this worker
has already had. Past the end of the table the last entry repeats.

**3.5** A scheduled restart whose due time is at or before the current time is
dispatched after every record, before health is evaluated. It records a
`restarted` event, sets the worker running, sets its last heartbeat to the
current time, and increases its consecutive restart count.

**3.6** A worker that has been running for at least `reset_after_ms` since it
last started has its consecutive restart count set back to zero. This is checked
after every record. Its restart history is not cleared.

## 4. Work in hand

**4.1** A `work` record gives a running or draining worker a unit of work. A
second `work` record for a worker that already has some replaces nothing and is
not an error.

**4.2** A `finished` record takes the work away. A `work` or `finished` record
for a worker that is neither running nor draining is ignored, and is not an
error.

**4.3** A crash takes the work away too. Work is not carried across a restart.

## 5. Draining

**5.1** A `drain` record asks a running worker to stop. If it has no work in
hand it stops at once, records `drained`, and becomes `stopped`.

**5.2** If it has work in hand it becomes `draining` and records nothing yet. It
records `drained` and becomes `stopped` when its work finishes.

**5.3** A draining worker is still checked for health. If it goes unhealthy or
crashes it follows section 3 as usual, and is no longer draining.

**5.4** A `stopped` worker is never restarted, never drained again, and never
evaluated for health.

**5.5** Draining a worker that is not running is ignored, and is not an error.

## 6. Report

**6.1** `events` lists every event in the order it happened, each with `t`,
`worker` and `kind`, one of `crashed`, `failed`, `restarted` or `drained`.

**6.2** `workers` reports each configured worker in configuration order, with
`name`, `state` (`running`, `down`, `draining`, `stopped` or `failed`),
`restarts` (the total number of `restarted` events for that worker) and
`crashes` (the total number of `crashed` events for that worker).

**6.3** `errors` lists each unknown worker in the order it was read, with `code`
and `detail`.
