# Rotation specification

This document specifies how a secret is rotated across environments. The replay
tool must reproduce it exactly.

`archive/` holds one capture from the live runner beside that run's own log.
Where any other document in this repository disagrees with the log, the log is
what the runner did.

## 1. Clock

Time is an integer second counter. Every event carries the clock at the moment
the runner recorded it.

## 2. Consumers and environments

**2.1** Environments are listed in the configuration in rollout order.

**2.2** A consumer belongs to one environment. Registering a consumer id that
already exists moves it to the new environment and keeps its acknowledgements.

**2.3** A consumer in an environment the configuration does not list produces the
error `UNKNOWN_ENV` and is not registered.

**2.4** An environment's health starts healthy and changes only when a `health`
record says so. A `health` record for an unlisted environment produces
`UNKNOWN_ENV`.

## 3. Versions

**3.1** A secret starts at version 1, which is live and requires no
acknowledgement.

**3.2** Rotating produces the next version, one higher than the highest version
that secret has ever had.

## 4. Starting a rotation

**4.1** `rotate` with `dry_run` records a `plan` event naming the version it
would create and the environments in rollout order, and changes nothing at all -
not the version counter, not the in-flight state.

**4.2** `rotate` while a rotation of that secret is already in flight produces
`ROTATION_IN_FLIGHT` and changes nothing.

**4.3** Otherwise the new version becomes in flight and the first environment
begins staging immediately, recording a `stage` event.

## 5. Acknowledgements

**5.1** An `ack` names a consumer and a version. An ack from a consumer that is
not registered produces `UNKNOWN_CONSUMER`.

**5.2** Acks are remembered per consumer and version whenever they arrive.

**5.3** An ack for a version that does not exist is remembered anyway and simply
never matches anything.

## 6. Completing a stage

A stage is evaluated after every record.

**6.1** The staging environment completes when every consumer registered in it
has acked the in-flight version **and** the environment is healthy. An
environment with no consumers completes as soon as it is healthy.

**6.2** Completing records a `complete` event, then the next environment in
rollout order begins staging and records a `stage` event, and that environment
is evaluated in turn.

**6.3** When the last environment completes, the rotation is done: a `rotated`
event is recorded, the new version becomes the current version, and the previous
current version enters its grace period starting at that moment.

## 7. Rollback

**7.1** If the staging environment becomes unhealthy, the rotation rolls back. A
`rollback` event is recorded for every environment the rotation had touched,
including the one that was staging when it failed. `archive/` shows the order
the runner writes them in.

**7.2** After a rollback the in-flight version is discarded. The current version
is unchanged, and acknowledgements for the discarded version are forgotten.

**7.3** A rollback does not put the current version into a grace period.

## 8. Revocation

**8.0** A `policy` record sets `grace_seconds` for the fleet from that moment.
`grace_seconds` in the `config` record is the fleet's starting policy.

**8.1** A version in its grace period is revoked once `grace_seconds` have
elapsed since its grace period began. `archive/` shows exactly where the runner
puts that boundary. This is checked after every record.

**8.2** Revoking records a `revoked` event naming the revoked version.

**8.3** A version that is in its grace period when a new rotation completes is
revoked at that moment regardless of its grace period, because only two versions
may ever be live at once.

## 9. Report

**9.1** `events` lists every event in the order it happened, each with `t`,
`kind` and the fields its kind defines: `plan` has `version` and `envs`; `stage`,
`complete` and `rollback` have `env` and `version`; `rotated` and `revoked` have
`version`.

**9.2** `errors` lists each error in record order, with `code` and `detail`.

**9.3** `state` reports `current`, the current version, and `live`, every version
still live, ascending.
