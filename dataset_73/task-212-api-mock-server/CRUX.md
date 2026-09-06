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

### B - Route precedence is segment-wise leftmost-literal, not most-literal-segments — and the shipped linter asserts the wrong rule (B + D + C)

**Mechanism.** Delete the giveaway sentence in environment/docs/mock-spec.md §2.4 ("Among the remaining candidates the one with the most literal segments wins. A tie is broken by declaration order, earliest first.") and replace it with: "Among the remaining candidates exactly one answers. The mock must resolve an overlap the way the production gateway resolves it; docs/gateway-routing.md records the gateway's decisions and is normative." Ship environment/docs/gateway-routing.md: a ~10-row table generated from the gateway's conformance suite, each row giving the templates in declaration order, the request path, and the winning template. The true rule is the one real gateways use: compare the two templates segment by segment from the left, and at the first position where one has a literal and the other a parameter the literal wins; only two templates with an identical literal/parameter mask fall through to declaration order. Rows that force that inference and rule out every competitor: (1) [0] /{tenant}/settings/theme/mode vs [1] /acme/{a}/{b}/{c} on /acme/settings/theme/mode -> route 1 wins (kills most-literals, 3 literals lose to 1); (2) [0] /files/{bucket}/raw/{key} vs [1] /files/logs/{a}/{b} on /files/logs/raw/x -> route 1 wins (equal literal counts, kills count+declaration-order); (3) [0] /v1/{c}/{d}/tail vs [1] /v1/{a}/logs/{b} on /v1/x/logs/tail -> route 1 wins (kills longest-literal-prefix, which ties and would pick route 0); (4) [0] /{a}/{b}/c vs [1] /{x}/{y}/c on /p/q/c -> route 0 wins (pins the identical-mask tie-break); plus four confirming rows (literal beats parameter, method never consulted). One sentence in gateway-routing.md guarantees uniqueness without naming the rule: "the gateway's choice depends only on the two templates, never on the request path, and never on declaration order except between two templates of identical shape." Misdirection (C): ship environment/devtools/contract_lint.py, the platform team's overlap warner, whose shadowed() computes specificity as len(literal segments) and prints "route 1 GET /acme/{a}/{b}/{c} is shadowed by route 0 GET /{tenant}/settings/theme/mode (more literal segments)" — i.e. the exact wrong rule, stated as the tool's own heuristic, with a stale comment that requests are replayed in file order (which also misdirects on crux E). It is a convenience script, never referenced as normative; mock-spec.md names gateway-routing.md as the authority, so authority ordering is explicit and there is no ambiguity. I verified that switching the reference model to leftmost-literal changes the output of ZERO of the 45 existing captures, so this is purely additive and no existing expectation moves.

**The wrong answer it punishes.** specificity = number of literal segments, tie broken by declaration order — which is what mock-spec.md currently says, what solution/repo/mockserver/routing.py::specificity() computes, what solution/repo/README.md asserts ("a route with more literal segments always beats one with more parameters"), and what the shipped linter prints. It agrees with leftmost on every visible sample and on all 6 overlapping requests in the current held-out corpus, and disagrees on the three new shapes above.

**How it is recoverable.** environment/docs/gateway-routing.md rows 1-4 are jointly satisfiable by exactly one behaviour (lexicographic literal>parameter mask comparison, ties to declaration order); rows 1, 2 and 3 individually eliminate most-literals, count+declaration-order and longest-prefix, and row 4 pins the tie-break. mock-spec.md §2.4 points at that file and calls it normative, and instruction.md's "where this file and those disagree, those win" clause already establishes docs as authority over narrative.

### E - The capture is in collector order, not handling order — and the request counter wraps

**Mechanism.** Every request gains a required `seq`: the value of the mock's 16-bit request counter when it handled that request. capture-format.md documents the field mechanically ("the counter increases by one per request handled and wraps from 65535 to 0; a capture holds one unbroken run of the counter") and adds "`requests` is in the order the collector's workers flushed them, which is not the order the mock handled them". mock-spec.md gains §7: "7.1 The mock handles requests in counter order. 7.2 The report lists responses in the order the capture lists the requests." The consequence is deliberately left latent: all mock state — which fixtures have already answered, and therefore which fixture answers next (§5.4) — evolves in counter order, while `responses` and `matched` stay in file order. So a capture whose file order is [B(seq 4102), A(seq 4101)] with a `times: 1` first fixture must report the SECOND fixture for B and the FIRST for A. On top of that, held-out captures include runs that cross the wrap (…65534, 65535, 0, 1…), where sorting by the raw seq value is wrong; the run being contiguous makes the reconstruction unique (find the value whose predecessor mod 65536 is absent, then order by (seq - first) mod 65536). Samples keep contiguous ascending seqs in file order, so they stay benign and expected.json is byte-identical.

**The wrong answer it punishes.** Iterate `capture["requests"]` in file order and ignore `seq` entirely (what the current solution and reference model do, and what the shipped linter's stale comment asserts). Second-order wrong default: `sorted(requests, key=lambda r: r["seq"])`, correct for every non-wrapping capture and wrong for the three wrap captures. Third: sorting the report itself into seq order, which breaks response ordering on every shuffled capture.

**How it is recoverable.** environment/docs/capture-format.md documents `seq` and the wrap; mock-spec.md §7.1/§7.2 state handling order and report order as separate facts. The binding evidence is environment/reference/r01.capture + recorded.json (shuffled seqs with a `times: 1` fixture, where the answers are visibly swapped relative to file order) and r02.capture (a run crossing 65535 -> 0 with `times: 2`), both recorded from the live mock and declared normative by a new mock-spec.md §8 ("the recordings in reference/ were taken from the live mock and settle anything this document leaves open").

### I - The contract in force as of the request's counter, not the contract at the end of the file

**Mechanism.** The mock watches its contract file and hot-reloads it, so a capture recorded across a deploy carries both contracts. Captures gain an optional `reloads`: an ordered list of `{"at": <counter value inside this capture's run>, "routes": [...]}`. Each request must be answered by the newest reload whose `at` is at or before the request's own counter position, falling back to the top-level `routes`. capture-format.md documents only the SHAPE of the field plus an honest TODO — "TODO(platform): document how `reloads` lines up with the request counter; the recordings in reference/ are the record for now" — which is a completely ordinary state for a format doc and keeps the as-of decision out of prose. Three sub-decisions are pinned by the recordings rather than stated: (a) selection is by the request's counter value, not by the request's position in the file (entangling this with crux E — a post-reload request written first in the file must still see the new contract, and a pre-reload request written last must still see the old one); (b) `matched` is the index into the route list in force for that request, so the same route reports a different index either side of a reload; (c) a reload swaps the whole route list, so every fixture in the new list starts unused and a `times: 1` fixture can answer again after the reload. The `at` value is unwrapped with the same run reconstruction as crux E, so a capture can wrap and reload.

**The wrong answer it punishes.** Merge or ignore reloads and serve everything from one contract — most plausibly the last one, which is the classic "use the current value instead of the as-of value" bug and is exactly the drift the task's own narrative complains about (the mock answering a path the service did not have yet). The next most plausible defaults are applying a reload when the loop reaches it in file order (correct only when file order happens to equal counter order), reporting `matched` against the initial `routes`, and carrying fixture tallies across a reload.

**How it is recoverable.** environment/reference/r03-r05.capture with recorded.json pin all three sub-decisions: r03 has a route that exists only in the initial contract (answered for a pre-reload request, 404 no_route for a post-reload one) and a route that exists only after (the mirror image); r04 writes the post-reload request first in the file and moves a route between index 1 and index 0 across the reload, so both the by-counter selection and the index base are readable off one file; r05 has a `times: 1` fixture consumed before the reload and answering again after. mock-spec.md §8 makes reference/ normative where the docs are silent, and instruction.md gains success criterion 7 ("running the tool on /app/reference reproduces /app/reference/recorded.json exactly"), so the recordings are contractual rather than decorative.

### G - HEAD is answered by the GET route, never has a body, and appears in the allow header

**Mechanism.** The task's own premise is that the mock must not differ from the real service; RFC 9110 says HEAD is GET without a body, and every real gateway implements it implicitly. Four coupled behaviours, none of them written in mock-spec.md: (1) a HEAD request whose candidates include a GET route is answered by that route — the same precedence rule then picks among the GET candidates — and the fixture IS consumed, so a following GET gets the next fixture; (2) an explicitly declared HEAD route beats the implicit GET one; (3) every response to a HEAD request carries `"body": null`, including the 404 no_route, the 405, the 400 refusals and the no_fixture 404 — one total rule rather than a special case; (4) the allow header on a 405 lists the methods the candidates *answer*, so HEAD is included whenever a GET candidate exists and is not duplicated when a HEAD route is declared (candidates GET+PUT -> "GET, HEAD, PUT"; candidates POST+PUT -> "POST, PUT"). The only prose change is §2.3, from "listing the candidates' methods" to "listing the methods the candidates answer", which is the hook rather than the answer. No existing capture uses HEAD (I checked: only GET, POST, PUT, DELETE appear), so nothing existing moves.

**The wrong answer it punishes.** Treat HEAD as just another method string: a HEAD request against a GET-only route becomes a 405 (or a 404 if the method is filtered before the path), the allow header omits HEAD, and any response that is produced carries the fixture body. Also plausible and also wrong: answering HEAD from the GET fixture but leaving the body in, or suppressing the body only on 2xx.

**How it is recoverable.** environment/reference/r06-r08.capture with recorded.json pin all four: r06 is HEAD then GET against a route whose first fixture has `times: 1` (pins both the implicit match and the consumption, and shows body null on a 200); r07 declares GET and HEAD on the same template and then sends a POST (pins the explicit-HEAD preference and the allow string "GET, HEAD"), plus a second contract with GET+PUT candidates giving "GET, HEAD, PUT" and a POST+PUT one giving "POST, PUT"; r08 sends a HEAD to an unrouted path and a HEAD that fails query validation, both recorded with body null, which generalises the rule to non-2xx. mock-spec.md §8 makes reference/ normative where the document is silent, and §2.3's "methods the candidates answer" flags that the allow set is not just the declared strings.

## Is it still solvable?

Every crux is settled by an artifact that ships inside environment/ and that mock-spec.md explicitly names as normative, so a careful reader converges on one answer with certainty rather than guessing. Precedence: docs/gateway-routing.md is a recorded decision table whose rows 1-4 are jointly consistent with exactly one behaviour, and the table states that the gateway's choice depends only on the two templates and falls back to declaration order only between identical shapes, which closes off path-dependent readings. Counter order, reloads and HEAD: environment/reference/ ships eight captures WITH their true reports, recorded from the live mock, and a new success criterion makes reproducing them contractual. That gives a strong model a local oracle it can run its own tool against and diff — it can discover it is wrong before the verifier does, which is the lifeline that keeps this above the 0.6 gate, while the held-out corpus uses different shapes (three-way overlaps, a wrap combined with a reload, HEAD against a route chosen by precedence) so the recordings cannot be memorised into a pass. The reward stays continuous and the difficulty is genuinely graded: 24 test functions, of which 6 (runs, shape, samples, identical-mask tie, legacy validation family, determinism) a naive spec-transcription still passes for about 0.25; getting the precedence table right adds three; getting the counter order and wrap adds four; reloads add four; HEAD adds four; and the three global comparisons plus the recordings test require all four cruxes. A model that lands three of four cruxes scores about 0.75. Nothing here is a riddle: leftmost-literal precedence is what OpenAPI-style gateways actually do, capture files really are written in collector order by workers with a wrapping counter, mocks really do hot-reload their contract mid-recording, and HEAD really is implicit in GET — each crux is a bug report a practitioner has actually filed against a mock server. Rule 3 and rule 4 are preserved by construction: solution/ and tests/reference_mock.py change in the same edit, and environment/ still ships no code at all, so the starting state has no /app/run.sh and fails every test. Rule 7 is preserved measurably: I ran leftmost-literal precedence against all 45 existing captures and it produces byte-identical output, seqs are added ascending so existing handling order is unchanged, and no existing capture uses HEAD or reloads — so every current expectation survives and the new corpus is purely additive.

## What was easy about it before

The task has repo *shape* (narrative instruction.md, benign environment/samples, hostile tests/captures, independent tests/reference_mock.py) but engine *content*: environment/docs/mock-spec.md is a complete, numbered specification that hands over every single decision the held-out corpus checks. §2.4 literally says "the one with the most literal segments wins. A tie is broken by declaration order, earliest first."; §2.3 gives the allow header format ("sorted and joined with `, `"); §3.3 gives the exact int grammar ("an optional `-` followed by digits and nothing else") and the exact bool literals; §4.4 gives the query-before-body order; §4.5 gives "after every declared field has passed, in ascending field name order"; §5.4 gives per-fixture exhaustion. tests/reference_mock.py is a line-for-line transcription of that document, and every one of the 39 held-out captures probes only a rule the document already states. So the whole task reduces to "translate mock-spec.md §1-§6 into Python" — which is exactly what a mid-tier model already does well. tools/check_shortcuts.py proves the *corpus* discriminates 19 near-misses, but every one of those 19 is a near-miss only for someone who did not read the spec sentence that settles it, so the discrimination measures carelessness, not engineering. Secondary weakness: only 6 test functions (3 of which are the same global comparison sliced three ways), so reward is nearly all-or-nothing and there is no partial credit surface. I verified that the whole visible+held-out corpus is currently insensitive to the precedence rule beyond what the spec states: only 6 of 58 held-out requests have more than one candidate template at all.

## Measured, not asserted

`tools/check_crux.py` implements each wrong answer described above,
runs the full behaviour suite against it, and reports what the suite
catches. This is its output:

```
docs/gateway-routing.md
  most_literals    reproduces the whole table: False
  most_params      reproduces the whole table: False
  first            reproduces the whole table: False
  longest_prefix   reproduces the whole table: False
  leftmost         reproduces the whole table: True (the only one that does)

control: solution/repo -> 26/26 tests pass

crux wrong default                                                    samples  suite
----------------------------------------------------------------------------------------------------
B   precedence is a count of literal segments, ties by declaration order pass     20/26  (0.77)
      x test_bodies_and_headers_match
      x test_matched_routes_match
      x test_precedence_is_not_a_count_of_literal_segments
      x test_precedence_when_literal_counts_and_prefixes_tie
      x test_precedence_among_more_than_two_candidates
      x test_head_is_answered_by_the_get_route
B   precedence is the length of the leading run of literal segments  pass     22/26  (0.85)
      x test_bodies_and_headers_match
      x test_matched_routes_match
      x test_precedence_when_literal_counts_and_prefixes_tie
      x test_precedence_among_more_than_two_candidates
E   requests are replayed in the order the file lists them           pass     19/26  (0.73)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_recorded_report_is_reproduced
      x test_handling_order_follows_the_counter
      x test_counter_wrap_is_reconstructed
      x test_fixture_state_evolves_in_counter_order
      x test_reload_replaces_the_route_list_outright
E   requests are replayed sorted by the raw seq value                pass     22/26  (0.85)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_recorded_report_is_reproduced
      x test_counter_wrap_is_reconstructed
E   the report itself is emitted in handling order                   pass     16/26  (0.62)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_matched_routes_match
      x test_recorded_report_is_reproduced
      x test_handling_order_follows_the_counter
      x test_counter_wrap_is_reconstructed
      x test_report_stays_in_file_order
      x test_fixture_state_evolves_in_counter_order
      x test_reload_selection_ignores_file_order
      x test_reload_replaces_the_route_list_outright
I   reloads are ignored and everything is served from the first contract pass     18/26  (0.69)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_matched_routes_match
      x test_recorded_report_is_reproduced
      x test_contract_in_force_is_the_one_at_the_request_counter
      x test_reload_selection_ignores_file_order
      x test_matched_is_indexed_against_the_live_contract
      x test_reload_replaces_the_route_list_outright
I   everything is served from the last contract in the file          pass     18/26  (0.69)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_matched_routes_match
      x test_recorded_report_is_reproduced
      x test_contract_in_force_is_the_one_at_the_request_counter
      x test_reload_selection_ignores_file_order
      x test_matched_is_indexed_against_the_live_contract
      x test_reload_replaces_the_route_list_outright
I   a reload applies once the loop reaches it in file order          pass     20/26  (0.77)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_matched_routes_match
      x test_recorded_report_is_reproduced
      x test_reload_selection_ignores_file_order
      x test_reload_replaces_the_route_list_outright
I   matched is reported against the contract the capture opens with  pass     21/26  (0.81)
      x test_matched_routes_match
      x test_recorded_report_is_reproduced
      x test_contract_in_force_is_the_one_at_the_request_counter
      x test_reload_selection_ignores_file_order
      x test_matched_is_indexed_against_the_live_contract
I   fixture tallies carry across a reload                            pass     22/26  (0.85)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_recorded_report_is_reproduced
      x test_reload_replaces_the_route_list_outright
G   HEAD is just another method string                               pass     18/26  (0.69)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_matched_routes_match
      x test_recorded_report_is_reproduced
      x test_head_is_answered_by_the_get_route
      x test_declared_head_route_is_preferred
      x test_head_response_never_has_a_body
      x test_allow_header_lists_the_methods_answered
G   HEAD is answered by the GET route but keeps the body             pass     20/26  (0.77)
      x test_bodies_and_headers_match
      x test_recorded_report_is_reproduced
      x test_head_is_answered_by_the_get_route
      x test_declared_head_route_is_preferred
      x test_head_response_never_has_a_body
      x test_allow_header_lists_the_methods_answered
G   the body is suppressed only on a 2xx                             pass     22/26  (0.85)
      x test_bodies_and_headers_match
      x test_recorded_report_is_reproduced
      x test_head_response_never_has_a_body
      x test_allow_header_lists_the_methods_answered
*   all four wrong defaults at once - the spec-transcription engine  pass     8/26  (0.31)
      x test_statuses_match
      x test_bodies_and_headers_match
      x test_matched_routes_match
      x test_recorded_report_is_reproduced
      x test_precedence_is_not_a_count_of_literal_segments
      x test_precedence_when_literal_counts_and_prefixes_tie
      x test_precedence_among_more_than_two_candidates
      x test_handling_order_follows_the_counter
      x test_counter_wrap_is_reconstructed
      x test_fixture_state_evolves_in_counter_order
      x test_contract_in_force_is_the_one_at_the_request_counter
      x test_reload_selection_ignores_file_order
      x test_matched_is_indexed_against_the_live_contract
      x test_reload_replaces_the_route_list_outright
      x test_head_is_answered_by_the_get_route
      x test_declared_head_route_is_preferred
      x test_head_response_never_has_a_body
      x test_allow_header_lists_the_methods_answered

OK: every wrong default reproduces the visible samples and every one is caught by the suite.
```

Two properties matter in that output. Every wrong answer is caught, so
the difficulty is real. And the scores in between are spread rather
than clustered at nought and one, so a partially correct implementation
earns partial credit - the reward stays continuous, which is what makes
the gap between a strong and a weak model measurable at all.
