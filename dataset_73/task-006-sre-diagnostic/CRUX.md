# CRUX — task-006-sre-diagnostic

Reviewer-facing note. What makes this task hard, why each hard part has exactly
one defensible answer, and which tests punish the wrong one.

**Task shape.** `SreDiagEngine.add/diagnose/reset/configure` — ingest a window
of host telemetry samples and return one root-cause verdict.

**What changed.** `instruction.md` used to be a transcription target: it handed
over all six threshold constants in a four-row table, the comparison
directions, the evaluation order, an explicit "compare the first sample to the
last", and two worked examples that produced the exact dicts two tests
asserted. Every numeric constant is now gone from `instruction.md`. The
specification lives in five documents under `environment/docs/` plus six
reviewed incident captures under `environment/samples/incidents/`. The one-line
rule summary that leaked verbatim into eleven files (including three that ship
to the agent) has been replaced with a neutral header everywhere.

**Existing coverage was preserved, not weakened.** All 13 original tests are
byte-identical and all 13 still pass against the new reference. That is by
construction: policy revision `r1` reproduces the exact constants the old spec
hardcoded, every legacy window sits in the `r1` era, is already in time order,
contains no counter restart, and spans exactly 60 seconds — the one span where
a per-minute rate and a raw window difference coincide exactly. 29 tests were
added on top, for 42 total.

---

## Crux I — stale authority: the revision in force at the window start governs

**Wrong default.** Read `environment/docs/threshold-policy.md` as ordinary
config and compile in the last (newest, `r3`) row — or scrape the numbers off
the retired v1 runbook and never notice the table is dated at all. A third
near-miss: apply the revision in force when the window *closed*.

**Why the right answer is unique.** The table has an `effective_from` column in
epoch seconds and cannot be read without seeing it; after the strip it is the
only place in the repository any threshold number appears. §3 of
`environment/docs/runbook-incident-classification.md` states the selection rule
in a paragraph about reproducibility — the verdict must be the one the on-call
engineer actually saw — and pins first-sample-versus-last-sample explicitly.
Independently, the labelled capture `inc-2024-0902-d.json` is an `r2`-era
window recorded as `NO_FAULT` that both `r1` and `r3` would classify as a disk
cascade, so sample-fitting alone forces the same reading.

**Tests.** `test_r2_era_window_uses_r2_disk_and_gc_lines`,
`test_r1_era_cpu_line_is_not_the_newest_cpu_line`,
`test_r1_era_memory_line_is_not_the_newest_memory_line`,
`test_r2_era_memory_line_is_neither_r1_nor_r3`,
`test_straddling_window_is_judged_by_the_revision_it_opened_under`,
`test_window_opening_exactly_on_a_revision_boundary_uses_the_new_revision`,
`test_shipped_incident_captures_replay_to_their_recorded_verdicts`.

`tools/check_crux.py` rivals: `newest-policy` 27/42, `oldest-policy` 38/42,
`policy-at-end` 41/42.

---

## Crux E+H — add() receives arrival order, not time order

**Wrong default.** `a, b = self._samples[0], self._samples[-1]` — literally
what the old reference did and what the deleted instruction sentence
instructed. Plus: `if len(self._samples) < 2` counting raw samples rather than
distinct timestamps, and no minimum-span check at all.

**Why the right answer is unique.** §2 of
`environment/docs/collector-agent.md` documents the forwarder as best-effort
UDP with retransmit: a dropped sample is re-sent and lands *after* samples
newer than itself, and the re-sent copy carries the same timestamp with the
corrected reading and supersedes the original. It then states the two required
steps in order — collapse duplicate timestamps keeping the most recently
received copy, then sort ascending. §2 of the runbook puts both admissibility
guards on that reconstructed window and states the 30-second minimum
numerically, with the boundary called out as admissible, so nothing is guessed.
`inc-2023-1211-b.json` is a labelled window recorded in genuine arrival order
containing a superseding duplicate; its label is reproducible only under
timestamp ordering *and* last-write-wins. `inc-2023-0715-f.json` is an
18-second window labelled `INSUFFICIENT_DATA`.

**Entanglement (H).** Reset detection walks consecutive pairs, so a window
sorted *after* reset detection yields different counter totals from one sorted
before it, and the span divisor differs too —
`test_ordering_is_applied_before_counter_reset_detection` isolates that
coupling.

**Tests.** `test_window_is_ordered_by_timestamp_not_arrival`,
`test_window_first_sample_is_earliest_not_first_arrival`,
`test_duplicate_timestamp_is_superseded_by_the_later_arrival`,
`test_repeated_single_timestamp_is_insufficient_data`,
`test_window_shorter_than_minimum_span_is_insufficient_data`,
`test_span_of_exactly_thirty_seconds_is_admissible`,
`test_ordering_is_applied_before_counter_reset_detection`,
`test_capstone_ordering_reset_and_policy_era_together`.

Rivals: `arrival-order` 37/42, `first-write-wins` 39/42, `naive-guards` 39/42,
`no-span-guard` 40/42, `inclusive-span` 40/42.

*Note for the sceptic:* the distinct-timestamp guard is deliberately not tested
in isolation from the span guard, because it cannot be — a window with one
distinct timestamp has span 0 and is rejected by the span check anyway. The
`naive-guards` rival breaks both together, which is how an implementer who
skipped runbook §2 actually writes it.

---

## Crux B+D+H — cumulative counters that reset, compared as per-minute rates

**Wrong default.** `b.disk - a.disk > 100`: subtract the endpoints, compare to
the number in the table. Across an agent restart that difference goes strongly
negative, the disk cascade silently disappears and the incident is handed to
`CPU_BOTTLENECK` — the exact misdiagnosis this classifier exists to prevent.
On a five-minute window the un-normalised difference over-fires; on a
thirty-second window it under-fires. Both directions are reachable.

**Why the right answer is unique.** This one requires *joining two documents*.
`collector-agent.md` §1 maps the five ingest parameters onto the platform
series they carry (`disk` → `disk_io_ops_total`, `net` → `net_bytes_total`,
`gc` → `gc_pause_ms_total`, `cpu`/`mem` → `_pct`). `metric-naming.md` states
that `_total` denotes a counter cumulative since process start that
reinitialises to zero on restart, while `_pct` denotes an instantaneous gauge.
The sentence "apply counter-reset handling to disk, net and gc" is written
nowhere; it falls out of the join. `collector-agent.md` §3 then gives the
recovery rule and explicitly rules out the rival reading: because the counter
restarts at zero, the restart step contributes *the post-restart reading
itself*, not zero, and "the second branch is not skip the step". The capture
`inc-2024-0318-c.json` is numerically chosen so that the drop-the-step reading
produces a different label, so the detail is pinned by data as well as prose.

Rate normalisation comes from the policy table's own column headers
(`disk_io_rate_per_min`, `gc_pause_ms_per_min`, `net_rate_per_min`) and is
restated with a formula in runbook §4, which also separates counter thresholds
(rates) from gauge thresholds (absolute reading of the last in-window sample).
No visible sample uses a non-60-second window except `inc-2025-0207-e.json`,
which is a 300-second window whose recorded verdict is only reproducible once
rates are normalised — so the rule is recoverable by reading and confirmable by
replay, but not by curve-fitting.

**Entanglement (H).** `MEM_PRESSURE` carries `secondary: GC_PRESSURE` only when
the gc *rate* crossed, which couples the counter arithmetic to an output field;
across a restart that rate is only visible once the reset is reconstructed.
This also finally gives `net` a job — it was previously accepted by `add()` and
read by nothing.

**Tests.** `test_counter_reset_preserves_the_disk_cascade`,
`test_counter_reset_step_contributes_the_post_restart_reading`,
`test_flat_counter_step_is_not_treated_as_a_restart`,
`test_counter_rates_are_per_minute_over_the_window_span`,
`test_long_window_is_not_inflated_by_raw_differences`,
`test_mem_pressure_gains_gc_secondary_only_when_the_gc_rate_crossed`,
`test_mem_pressure_omits_secondary_when_gc_is_quiet`,
`test_gc_rate_exactly_on_its_threshold_does_not_complete_the_cascade`,
`test_net_rate_exactly_on_its_threshold_does_not_fire`.

Rivals: `raw-delta` 36/42, `drop-reset-step` 36/42, `no-rate-norm` 38/42,
`always-secondary` 41/42, `const-cpu-suspect` 40/42.

---

## Crux C — the repository actively points at the wrong answer

Three artefacts, each of the kind a practitioner really does trip over, and
each refutable from `environment/` alone.

1. **`environment/tools/triage_report.py`** — a legacy on-call helper imported
   by nothing. It embodies all three wrong defaults at once: arrival-order
   endpoints, raw differences with no reset handling and no normalisation, and
   the newest (`r3`) thresholds hardcoded. Run against
   `inc-2024-0318-c.json`, whose shipped label is `DISK_IO_SATURATION`, it
   prints:

   ```
   ROOT CAUSE: CPU_BOTTLENECK  (disk delta -910.0 ops - disk ruled out)
   ```

   It disagrees with five of the six shipped labels (it happens to agree
   only on `inc-2023-0402-a.json`, the clean 60-second in-order capture). A model that mirrors it
   inherits every wrong default in one move (`triage-tool` rival: **16/42**);
   a model that runs it against the captures catches it lying and gets a strong
   signal about what is actually going on. `environment/tools/README.md` states
   the tiebreak in one line: if the tool disagrees with a capture's recorded
   verdict, the capture is right.

2. **The stale comment at the top of that tool** —
   `# NOTE: disk/gc are gauges, so a plain last-minus-first delta is exact.` —
   flatly contradicted by the `_total` suffixes in `collector-agent.md` §1.
   This is the single sentence most likely to talk a skimmer out of crux B+D.

3. **`environment/docs/retired/runbook-v1.md`** — the pre-2023 playbook,
   carrying `status: RETIRED` and
   `superseded_by: ../runbook-incident-classification.md` in its front matter.
   It specifies the CPU rule *before* the disk cascade and quotes absolute,
   non-rate thresholds. The in-force runbook's §7 changelog names it and says
   v1's ordering misrouted the 2023-11-04 incident. The contradiction is
   resolvable with certainty by anyone who reads front matter and changelogs,
   and not by anyone who greps the docs tree for a threshold table and takes
   the first hit. `instruction.md` §4 warns that documents on disk disagree and
   that each declares its own status, without saying which one wins.

---

## Solvability

Every crux is pinned by at least two independent artefacts inside
`environment/`, so no reading is left defensible-but-wrong:

| crux | prose evidence | second, independent evidence |
|---|---|---|
| I | `effective_from` column; runbook §3 reproducibility paragraph | `inc-2024-0902-d.json` (r2-era, differs under both r1 and r3) |
| E | `collector-agent.md` §2 retransmit/supersede; runbook §§1–2 (30 s stated numerically) | `inc-2023-1211-b.json`, `inc-2023-0715-f.json` |
| D | `collector-agent.md` §1 mapping joined to `metric-naming.md` `_total`; §3 recovery rule | `inc-2024-0318-c.json`, chosen so drop-the-step yields a different label |
| B | policy table `_per_min` headers; runbook §4 formula and counter/gauge split | `inc-2025-0207-e.json` (300-second window) |

Nothing requires guessing a constant.

## Reward continuity

42 tests, layered: 13 legacy (basic rule shape), 8 ordering/guards, 9
counters/rates/entanglement, 7 threshold policy, 4 network rule and computed
`cpu_suspect`, 1 capstone. Each crux earns credit on its own — a model that
handles counter resets but misses rate normalisation still banks the reset
tests. The measured spread across fifteen wrong-default implementations runs
from **16/42 (0.38)** for the model that mirrors the shipped triage tool,
through **22/42 (0.52)** for the pre-redesign baseline, up to **41/42 (0.98)**
for one that misses only the straddling-window policy rule. Floor is non-zero;
ceiling is attainable.

## Verification actually run

```
ENGINE_DIR=$PWD/solution/engine    pytest tests/test_outputs.py   -> 42 passed
ENGINE_DIR=$PWD/environment/engine pytest tests/test_outputs.py   -> 42 failed
ENGINE_DIR=$PWD/solution/engine    pytest tests/test_grader.py    -> 1 passed, score 1.0
python tools/check_crux.py       -> all 15 wrong-default rivals fail; reference 42/42
python tools/check_mutations.py  -> 14 mutations, 13 caught, 1 survivor
```

The single mutation survivor is `break` → `continue` in the policy-selection
loop, which is genuinely equivalent because `POLICY_REVISIONS` is sorted
ascending by `effective_from`.

The stub in `environment/engine/engine.py` is untouched: its
`NotImplementedError` bodies remain, and the grader's independent stub-marker
and byte-digest checks in `tests/test_grader_inner.py` continue to score it 0.0
regardless of the suite.
