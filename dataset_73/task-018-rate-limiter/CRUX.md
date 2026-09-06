# Why this task is hard

A hard task is only worth buying if it is hard for a legitimate reason.
This note names the reason, so a reviewer can check the claim rather than
take it on trust.

Every mechanism below hides the *path* to the answer. None of them hides
the *existence* of a single correct answer: for each one, the evidence
that makes the right behaviour recoverable ships inside `environment/`,
and is named here. A task with two defensible readings would be a defect,
not a difficulty.

## What a model has to work out

### I - Effective-as-of policy resolution (the row in force at the request instant, not the newest row)

**Mechanism.** The engine gains a real gateway feature: per-tenant policy rows. `config["policies"]` is a list of control-plane export rows `{"tenant", "capacity", "rate", "effective_at", "revision", "note"}`, mirrored on disk as environment/reference/policies.json. The key is `tenant:client_id`, tenant = the substring before the first colon (a key with no colon, or a tenant absent from the table, resolves against the `"*"` default row). For any instant t the governing row is `max by (effective_at, revision) over rows with effective_at <= t` — a single sentence that is written down NOWHERE and must be recovered from data. The shipped table is deliberately hostile in four ways a real control-plane export is: (a) rows are ordered by `revision`, not by `effective_at`; (b) revision 10 is a retroactive backfill whose effective_at is EARLIER than revision 4's, so "last row in the file" and "highest revision overall" are both wrong; (c) two rows share an effective_at (an amended publish, revisions 7 and 9 with capacities 6 and 3), so a tie-break on revision is forced; (d) a future-dated scheduled upgrade (acme, capacity 100, effective_at after the capture window) must not apply yet. When `policies` is absent, `capacity`/`rate` synthesise one implicit row effective at -inf, which is exactly what the 16 existing tests exercise, so they all keep passing untouched.

**The wrong answer it punishes.** Resolve the tenant policy once at construction, or take the last row in the list, or take the highest-revision row, or `max(rows, key=effective_at)` ignoring the `<= now` filter (which applies the scheduled future upgrade early and lets acme burst 100). Every one of these is the natural first implementation and every one is decisively wrong on the shipped capture.

**How it is recoverable.** environment/reference/policies.json shipped alongside environment/capture/trace-02-policy-rollout.jsonl. The trace's `tokens` readouts and first-touch burst lengths pin each sub-rule uniquely: a fresh key first touched at t inside the backfill span bursts to revision 10's capacity, not revision 4's (pins the retroactive row); a fresh globex key first touched after the amended publish gets exactly 3 allows then a deny, matching revision 9 and not revision 7 (pins the revision tie-break); acme is still denied at its old capacity at a timestamp after the scheduled row appears in the file but before its effective_at (pins the `<= now` filter); a key `zeta:7` whose tenant is absent from the table behaves at the `*` row's capacity, and a bare key with no colon does too (pins tenant extraction and default fallback). environment/docs/limiter-contract.md documents the row SHAPE and the key format only, and states in as many words that the resolution rule is whatever reproduces the decision log.

### H - Refill is integrated piecewise across policy edges, clamping to each segment's capacity

**Mechanism.** Crux I only decides which row governs an instant; this crux is the coupling it creates with bucket state. Because the bucket is only touched when a request arrives, an idle span can straddle one or more policy edges. Legacy behaviour is to walk the policy timeline between `last_update` and `now` and, for each segment, add `dt * rate_i` and clamp to `capacity_i` — so a capacity downgrade that lands mid-span truncates tokens AT the edge (and that truncation is not undone by later refill), while an upgrade grants nothing retroactively. The bucket's anchor is preserved across the change; the bucket is never recreated and never re-fills to full on a policy change. Concretely: cap 10 / rate 0.02 until the edge, cap 10 / rate 0.05 after; a bucket left at 1.0 tokens, read 90s later with the edge at +60s, must read 3.7 — flat-at-new-rate gives 5.5, flat-at-old-rate gives 2.8, recreate-full gives 10.0. Also entangled here: a fresh key's bucket starts full at the capacity in force AT FIRST TOUCH (not the default capacity), and a request whose cost exceeds the currently effective capacity is denied immediately and consumes nothing rather than waiting forever.

**The wrong answer it punishes.** Look the policy up once at request time and apply `elapsed * rate_now`, clamped once to `capacity_now`. This is what every from-scratch implementation does and what the shipped triage tool does. Secondary wrong defaults: rebuild the TokenBucket (full) when the policy changes; clamp only at the end of the walk so a downgrade's truncation is silently undone; treat `cost > capacity` as "retry later" and let the caller spin.

**How it is recoverable.** environment/capture/trace-05-downgrade.jsonl records `tokens` readouts that straddle one edge and two edges, in both directions (downgrade after the bucket is above the new cap, upgrade while the bucket is below it), with values chosen so the piecewise result, the flat-new-rate result, the flat-old-rate result and the recreate-full result are four distinct numbers. A `cost` larger than the effective capacity appears twice with `decision:false` and an unchanged `tokens_after`, pinning the deny-and-do-not-consume rule. environment/capture/README.md documents the JSONL field names and the gateway changelog, nothing about the arithmetic.

### E - The clock steps backwards: monotonic refill anchor, and a window timeline that is no longer sorted

**Mechanism.** The injected clock is wall time on an NTP-disciplined gateway host, and the captures contain a backwards step (the capture README's changelog notes the host was re-synced). Two invariants the obvious code assumes are violated at once. (1) Bucket: the refill anchor is a high-water mark — `last_update` never moves backwards, a call at a time earlier than the anchor grants zero tokens and does not rewind the anchor, so when time catches up only the span beyond the previous high-water mark is credited. (2) Window: the deque of admitted timestamps is therefore NOT sorted, so pruning must scan the entire timeline rather than popping a prefix, and the recorded timestamp is the raw `now` (the window is a log of observed arrival times, not of clamped times). The two rules are separately pinned so they cannot be conflated, and one capture line exercises both together.

**The wrong answer it punishes.** `elapsed = max(0.0, now - last_update)` followed by `last_update = now` — i.e. exactly what solution/engine/bucket.py does today. It clamps the negative elapsed but still rewinds the anchor, so the catch-up span is credited twice (2.0 tokens where the truth is 0.0, then 6.0 where the truth is 4.0). For the window, the textbook `while dq and dq[0] <= cutoff: dq.popleft()` stops at the first non-expired entry and leaves genuinely expired entries stranded behind it, over-counting the key forever.

**How it is recoverable.** environment/capture/trace-03-clock-step.jsonl. The bucket half records `tokens` readouts at three points around a 2.0s backwards step whose values are 2.0 / 2.0 / 4.0 under the monotonic anchor and 2.0 / 3.5 / 6.0 under the rewinding one. The window half records an isolated out-of-order case where the boundary is irrelevant (entries at 1000, 1001, then 995 after the step; a call at 1005.5 with window 10 and max 3 is ALLOWED, which is only possible if the stranded 995 entry was pruned by a full scan) and then a combined case that also crosses the boundary. Both halves are single-mechanism-per-line so the reader can attribute each observation.

### C - The shipped triage tool and the incident postmortem both name the wrong root cause (carrying the window-boundary wrong-default lure)

**Mechanism.** Two stale artifacts ship in environment/ and both point away from the truth, while the machine-generated capture points at it. (1) environment/tools/limiter_doctor.py is an unsupported internal triage CLI that reconstructs token levels from a capture and labels every deny. It contains the wrong-default implementation in readable form — a single flat `elapsed * rate` refill against the newest policy row, and window pruning with a strict `< cutoff` prefix pop — and prints diagnoses like `acme:10.0.0.4 deny at t=...: bucket exhausted, raise rate`. Its reconstructed `tokens` column visibly disagrees with the capture's recorded `tokens_after` on exactly the lines that matter, so running it is the fastest way to find the cruxes and copying it is the fastest way to fail. (2) environment/docs/incident-8812.md is a postmortem, headed "gateway 3.9", that asserts three wrong things: that policy changes take effect on publish (contradicting crux I), that the NTP step caused the bucket to refill too SLOWLY and the mitigation was to widen capacity (contradicting crux E, where the correct behaviour grants zero, not less), and that the window boundary bug was fixed by COUNTING the entry that lands exactly on `now - window_sec`. The truth is the opposite: the window is half-open `(now - window_sec, now]`, so an entry exactly at the cutoff is expired — the B-lure, and the mutant I confirmed the current suite cannot catch. The postmortem is provably stale rather than merely contradicted: capture/README.md's changelog lists `4.0 — scheduled policy rollout, effective_at honoured` and `4.2 — window boundary made half-open`, and every trace header carries `gateway_version: 4.3`.

**The wrong answer it punishes.** Believe the prose and the tool. Prune with `entry < cutoff` (retaining the boundary entry, so a key that has just aged out is still denied), resolve policies at publish time, and treat the clock step as a refill-starvation problem to be fixed by widening capacity. A model that reads only instruction.md plus the two most human-looking files in environment/ lands on all three.

**How it is recoverable.** environment/capture/trace-04-window-boundary.jsonl isolates the boundary with two adjacent lines: one admitted call at exactly `cutoff` (max_reqs=1, an entry at 1000 read at 1010 with window 10 — allowed only if the boundary entry expired) and one denied call at `cutoff + 1e-6` (allowed under a strict comparison, denied under the half-open one). environment/capture/README.md's version changelog plus the `gateway_version: 4.3` header on every trace makes the 3.9 postmortem verifiably out of date, and diffing limiter_doctor.py's printed reconstruction against the capture's own `tokens_after` column makes the tool verifiably wrong. There is exactly one behaviour consistent with the machine artifacts.

## Is it still solvable?

Every rule has exactly one value and every value is pinned by a machine-generated artifact inside environment/. The five capture traces are single-mechanism-per-line by construction, and each discriminating observation is numerically chosen so that the correct model and each plausible wrong model produce different numbers (e.g. the piecewise refill readout is 3.7 where flat-new-rate is 5.5, flat-old-rate is 2.8 and recreate-full is 10.0; the post-step token readouts are 2.0/2.0/4.0 versus 2.0/3.5/6.0). Nothing requires guessing a constant that is not written down somewhere: the policy table ships verbatim in reference/policies.json, the key format and row shape are documented normatively in docs/limiter-contract.md, and capture/README.md documents the JSONL field names and the version changelog. The path is the ordinary one a practitioner takes: read the contract for the API, read the export for the data shape, replay the traces by hand or with a scratch script, and notice where the shipped triage tool's reconstruction disagrees with the recorded truth. The misdirecting artifacts are falsifiable rather than merely contradictory — the postmortem is stamped gateway 3.9 while every trace is stamped 4.3, and the changelog names the two behaviour changes that landed in between — so a careful reader can justify discarding them, which is what keeps the answer unique. Reward stays continuous and the floor stays low: all 16 existing tests still pass under the new engine (absent `policies`, `capacity`/`rate` synthesise one implicit row effective at -inf, and none of them steps the clock backwards or touches the window boundary), so a naive-but-competent baseline scores 16/46 = 0.35, while a model that recovers the policy timeline, the piecewise refill and the two window rules but misses, say, the revision tie-break and the cost>capacity rule still scores ~0.9. The four cruxes are independently scored across the 30 new tests, so partial understanding earns partial credit rather than falling off a cliff.

## What was easy about it before

instruction.md is a complete transcription target. It states the refill formula literally ("refill the key's bucket to min(capacity, tokens + elapsed*rate)"), states the start state ("A key's bucket starts full"), states the entire sliding-window algorithm ("keep a per-key timeline of accepted calls; drop entries older than now - window_sec; if fewer than max_reqs remain, record now and return True"), and then Section 3 ships two worked examples with the exact expected output lists ([True, True, True, False] and [True, True, True, False, False]). Nothing has to be inferred; a mid-tier model transcribes 30 lines of textbook code. The suite is also blind to the only two subtleties the task claims to test: I verified that mutating solution/engine/engine.py's `dq[0] <= cutoff` to `dq[0] < cutoff` still passes 16/16, and that deleting the `max(0.0, now - self.last_update)` clamp in solution/engine/bucket.py also passes 16/16. Worse, the spec's own sentence ("drop entries older than now - window_sec", i.e. strictly older) contradicts the reference implementation, so the single latent decision in the task is currently documented backwards and untested. There is one configuration, one clock direction, and one policy — none of the multi-tenant, policy-rollout or clock-skew nastiness that the domain (an API gateway limiter) actually contains.

## Measured, not asserted

`tools/check_crux.py` implements each wrong answer described above,
runs the full behaviour suite against it, and reports what the suite
catches. This is its output:

```
reference engine: 47/47 passing

captures replayed against the reference
    trace-01-baseline.jsonl             11 lines, 0 mismatch
    trace-02-policy-rollout.jsonl       71 lines, 0 mismatch
    trace-03-clock-step.jsonl           13 lines, 0 mismatch
    trace-04-window-boundary.jsonl       9 lines, 0 mismatch
    trace-05-downgrade.jsonl            16 lines, 0 mismatch

naive limiter written from the prose alone
    19/47 passing
    crux tests failed  C:2/3  E:5/6  H:8/8  I:13/14
    all 16 legacy tests still pass (reward stays continuous)

[crux I] bites     policy resolved by highest revision (what limiter_doctor.py does)
           31/47 passing, 9 crux-I test(s) failed, 7 other
           - test_policy_row_in_force_at_first_touch
           - test_later_effective_at_supersedes_a_backfilled_row
           - test_row_effective_before_the_backfill_still_governs_earlier_instants
           - test_scheduled_row_does_not_apply_before_its_effective_at
[crux I] bites     policy is max(effective_at) with no 'in force yet' filter
           31/47 passing, 9 crux-I test(s) failed, 7 other
           - test_policy_row_in_force_at_first_touch
           - test_later_effective_at_supersedes_a_backfilled_row
           - test_row_effective_before_the_backfill_still_governs_earlier_instants
           - test_scheduled_row_does_not_apply_before_its_effective_at
[crux I] bites     effective_at tie broken the other way (first publish wins)
           45/47 passing, 1 crux-I test(s) failed, 1 other
           - test_amended_publish_wins_the_effective_at_tie
[crux I] bites     tenant taken as the whole key instead of the leading segment
           30/47 passing, 10 crux-I test(s) failed, 7 other
           - test_policy_row_in_force_at_first_touch
           - test_later_effective_at_supersedes_a_backfilled_row
           - test_row_effective_before_the_backfill_still_governs_earlier_instants
           - test_scheduled_row_does_not_apply_before_its_effective_at
[crux H] bites     flat elapsed*rate against the policy in force now
           42/47 passing, 5 crux-H test(s) failed
           - test_refill_integrates_across_one_policy_edge
           - test_refill_across_an_upgrade_edge_from_empty
           - test_refill_across_two_policy_edges
           - test_downgrade_truncation_is_not_undone_by_later_refill
[crux H] bites     segments summed, capacity clamped only at the end of the walk
           45/47 passing, 2 crux-H test(s) failed
           - test_refill_across_two_policy_edges
           - test_downgrade_truncation_is_not_undone_by_later_refill
[crux H] bites     bucket refilled to full whenever its policy changes
           42/47 passing, 5 crux-H test(s) failed
           - test_refill_integrates_across_one_policy_edge
           - test_refill_across_an_upgrade_edge_from_empty
           - test_refill_across_two_policy_edges
           - test_downgrade_truncation_is_not_undone_by_later_refill
[crux E] bites     negative elapsed clamped to zero but the anchor still rewinds
           45/47 passing, 2 crux-E test(s) failed
           - test_refill_anchor_does_not_rewind_on_a_backwards_step
           - test_catchup_credits_only_the_span_beyond_the_high_water_mark
[crux E] bites     window pruned by peeling a prefix off the front
           44/47 passing, 3 crux-E test(s) failed
           - test_window_prunes_entries_that_are_not_at_the_front
           - test_window_records_the_raw_arrival_time
           - test_window_out_of_order_entry_and_window_edge_together
[crux C] bites     window edge counted inclusively (what INC-8812 says was fixed)
           44/47 passing, 2 crux-C test(s) failed, 1 other
           - test_window_entry_exactly_on_the_edge_has_expired
           - test_window_edge_with_several_entries
[crux C] bites     the whole INC-8812 postmortem, believed
           24/47 passing, 2 crux-C test(s) failed, 21 other
           - test_window_entry_exactly_on_the_edge_has_expired
           - test_window_edge_with_several_entries

every wrong-default variant is caught by the tests that guard its crux, and the naive limiter still earns its legacy tests.
```

Two properties matter in that output. Every wrong answer is caught, so
the difficulty is real. And the scores in between are spread rather
than clustered at nought and one, so a partially correct implementation
earns partial credit - the reward stays continuous, which is what makes
the gap between a strong and a weak model measurable at all.
