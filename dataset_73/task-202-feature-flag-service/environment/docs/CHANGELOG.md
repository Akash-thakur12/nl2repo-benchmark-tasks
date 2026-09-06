# Flag service changelog

Only entries that changed evaluation semantics are kept here. The current
specification is `docs/flag-spec.md` (v3).

## v3.0.1 - 2024-11-02

Bucketing regression fixture exported to `docs/fixtures/bucketing.csv` after
INC-4471 so the reduction can be checked mechanically rather than argued from
prose. No behaviour change.

## v3.0 - 2024-10-28

### INC-4471: the flag editor regenerated `salt` on every save

Saving a flag in the editor allocated a fresh `salt`, which re-bucketed roughly
40% of users mid-rollout. Users who had been served `on` for a week started
seeing `off` because their bucket moved, not because anything about the ramp
changed.

From v3.0 the bucketing salt is allocated when a key is **created** and pinned
for the lifetime of the key. A later definition's `salt` is recorded in the
audit trail and ignored - `update` replaces `enabled`, `variants`,
`off_variant`, `default_variant`, `rules` and `prerequisites` wholesale, but the
salt in force stays the one recorded when the key was first defined. Deleting
the key releases the seed, so defining the key again afterwards allocates the
salt from that new definition.

Audit trail for the reproduction case, flag `salted`, user `erin`:

| definition | `salt` field | salt in force | bucket | v2 served | v3 serves |
| --- | --- | --- | --- | --- | --- |
| create, t=1 | `alpha` | `alpha` | 2340 | on | on |
| update, t=3 | `omega` | `alpha` (pinned) | 2340 | off | on |
| update, t=5 | `beta` | `alpha` (pinned) | 2340 | on | on |
| delete, t=7 | - | released | - | - | - |
| create, t=8 | `omega` | `omega` | 7390 | off | off |

The v2 buckets for the same user under the salts that were written are in
`docs/fixtures/bucketing.csv` (`salted,omega,erin,7390` and
`salted,beta,erin,4779`); under v3 neither is served while the key lives.

### INC-4602: prerequisite cycles

See `docs/incidents/INC-4602.md`. Changes what the evaluation reports; the
detection itself is unchanged.

### INC-4530: under-allocated rollouts

See `docs/incidents/INC-4530.md`. Changes what happens to traffic above the
rollout total.

## v2.4 - 2024-06-14

Last release of the v2 semantics. The v2 specification is retained at
`docs/attic/flag-spec-v2.md` for audit only. `tools/flagdoctor.py` has not been
rebuilt since this release and its diagnostics still describe v2 behaviour.
