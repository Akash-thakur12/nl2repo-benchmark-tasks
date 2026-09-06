# Runner outcome codes

Vendor reference for the `outcome` field every run carries. `outcome` is the
runner's own verdict for the build as a whole; it says nothing about any
individual test.

## Why the distinction matters

When a build dies for a reason that has nothing to do with the code - the agent
image cannot be pulled, the agent host disappears mid-build, a human presses
cancel - the runner still publishes a results block, because downstream
dashboards require one. Everything that had not yet reported by the time the
build died is written out as a **placeholder** row so that the block is
complete. Placeholder rows are indistinguishable from real ones by inspection:
they are ordinary `failed` or `error` rows, and occasionally carry a status
string the schema does not recognise, because the field is filled from whatever
the agent last reported. They are not observations of the test.

A run whose outcome does not publish real results is a run about which nothing
can be learned. Its results block exists, but no row in it is evidence.

## The table

| code         | meaning                                              | results are evidence |
|--------------|------------------------------------------------------|----------------------|
| `completed`  | the build ran to completion; every test reported     | yes                  |
| `failed`     | the build ran, and reported at least one failure     | yes                  |
| `timed_out`  | the build hit its wall clock limit after running     | yes                  |
| `infra_error`| the agent could not be prepared (image, disk, mount) | no                   |
| `agent_lost` | the agent stopped responding while the build ran     | no                   |
| `cancelled`  | a human or a superseding push cancelled the build    | no                   |

`timed_out` is in the "yes" column deliberately: the build ran, the tests that
reported did really report, and the wall-clock kill is recorded per build rather
than per test. `failed` is likewise a real build - it is simply a build in which
something failed, which is exactly the case the detector exists to look at.

No other code is emitted. The list is closed.
