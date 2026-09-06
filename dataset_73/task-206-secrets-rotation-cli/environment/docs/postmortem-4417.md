# Postmortem: rot-4417, credential rotation stalled then over-revoked

**Status: draft. Written from `tools/quicklook.py` output during the incident,
on the phone, at 03:40. Not reconciled against the runner log. Keep it for the
narrative; do not treat any timing in it as measured.**

Author: on-call (platform-security)
Capture: `archive/rot-4417.session`
Runner log: `archive/rot-4417.runner.log` (pulled afterwards, not yet read)

## What happened

We rotated the shared service credential across the fleet. Three things went
wrong and I think they have three separate causes.

### 1. v3 was revoked early

We dropped the retention window from 600s to 120s at 11:00 into the run
(`policy t=1100`). The policy change took effect immediately, so the version
that was already sitting in its grace period had its deadline recomputed and
went away at 1220 instead of the 1600 we had all diarised. Nobody was watching
at 1220. Recommendation: stop changing policy during a rotation.

### 2. The runner back-dated a completion

`billing-api`'s acknowledgement is stamped `t=180` in the capture, which is
*before* the `tick` at 250 that precedes it in the file. The runner completed
the `dev` stage off the back of that record and stamped the completion 180 -
i.e. it back-dated the completion to the acknowledgement's own timestamp. That
is why the dashboard shows `dev` finishing before the tick that we know had
already fired. Every event the runner writes carries the timestamp of the record
that caused it, so out-of-order merge records drag the whole timeline
backwards. Recommendation: stop merging the ack stream into the journal.

(I have this from quicklook, which reads the capture the same way the runner
does.)

### 3. `prod` went first

The runner walks the environments alphabetically, so `dev`, `prod`, `staging`.
That is not the rollout order anyone configured and it is why `prod` took the
new credential before `staging` had settled. Filed as a separate bug.

## Actions

- [ ] Freeze policy changes for the duration of a rotation.
- [ ] Stop merging streams into a single capture.
- [ ] Make the runner honour the configured rollout order.
- [ ] Someone read `archive/rot-4417.runner.log` and check the three claims
      above. I did not have it in front of me and quicklook is a scratch tool I
      wrote in ten minutes.
