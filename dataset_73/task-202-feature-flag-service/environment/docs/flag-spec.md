# Flag evaluation specification

Version 3 (current). This document specifies how our flag service resolves a
flag for a user. The replay tool must reproduce it exactly.

Three behaviours changed between v2 and v3: the bucketing salt in force across a
redefinition, what a prerequisite cycle reports, and what an under-allocated
rollout does. Each is covered below, with the audit trail named where the
service's own records are the authority. `docs/attic/` holds the retired v2
text; it is kept for audit only and is not normative.

## 1. Flag shape

A flag definition has:

- `key` - unique string
- `enabled` - boolean
- `variants` - non-empty list of variant names
- `off_variant` - the variant served when the flag is not enabled
- `default_variant` - the variant served when nothing else matches
- `salt` - string used in bucketing
- `rules` - ordered list, may be empty
- `prerequisites` - list, may be empty

A rule has `attribute`, `operator`, `values`, and exactly one of `variant` or
`rollout`. A prerequisite has `flag` and `variant`.

A `rollout` is a list of `{"variant": name, "weight": int}` whose weights are
non-negative and sum to **at most** 10000. Captures taken during a ramp
routinely contain a rollout that is only part-allocated.

## 2. Evaluation order

Evaluation returns a variant and a reason, and the steps are tried strictly in
this order. The first one that produces a result wins.

**2.1** If the flag is not defined, the result is variant `null` with reason
`FLAG_NOT_FOUND`.

**2.2** If `enabled` is false, the result is `off_variant` with reason `OFF`.

**2.3** Every prerequisite is checked, in list order. A prerequisite is
satisfied when evaluating its `flag` for the same user yields exactly its
`variant`. On the first unsatisfied prerequisite the result is `off_variant`
with reason `PREREQUISITE_FAILED`. A prerequisite naming a flag that is not
defined is unsatisfied.

**2.4** Rules are tried in list order. The **first** matching rule wins; later
matching rules are not consulted. A matching rule with a `variant` yields that
variant with reason `RULE_MATCH`. A matching rule with a `rollout` yields the
bucketed variant with reason `RULE_ROLLOUT` when the rollout selects one; see
§4.3 and `docs/incidents/INC-4530.md` for what happens when it does not.

**2.5** Otherwise the result is `default_variant` with reason `DEFAULT`.

## 3. Rule matching

**3.1** A rule reads `attribute` from the user context. If the context has no
such attribute, the rule does **not** match. A missing attribute is never
treated as null, empty or zero.

**3.2** Operators:

| operator | matches when |
| --- | --- |
| `in` | the attribute equals one of `values` |
| `not_in` | the attribute equals none of `values` |
| `starts_with` | the attribute is a string starting with one of `values` |
| `contains` | the attribute is a string containing one of `values` |
| `gt` | the attribute is a number strictly greater than `values[0]` |
| `lt` | the attribute is a number strictly less than `values[0]` |

**3.3** `in` and `not_in` compare with exact type equality: the string `"1"`
never equals the number `1`, and booleans never equal numbers.

**3.4** `starts_with` and `contains` require the attribute to be a string. If it
is not, the rule does not match - this is not an error.

**3.5** `gt` and `lt` require the attribute to be an `int` or `float` and not a
`bool`. If it is not, the rule does not match.

## 4. Bucketing

**4.1** The bucket is derived from a SHA-256 of the flag key, the salt and the
user key joined with colons in that order, reduced to an integer in
[0, 10000). The reduction is fixed by the service and pinned by
`docs/fixtures/bucketing.csv`; an implementation that reproduces every row of
that fixture is correct. The fixture is the acceptance condition for this
section - do not take a reduction from any other document.

**4.2** The flag key and the salt are both part of the hashed string, so the
same user falls in different buckets for different flags. Bucketing must never
be computed from the user key alone.

**4.3** Weights are **cumulative**. Walk the rollout in list order accumulating
weights; the first variant whose running total is strictly greater than the
bucket is the result. A variant with weight 0 can never be selected. Because
weights may sum to less than 10000 (§1), a bucket at or above the total is not
covered by the rollout at all; `docs/incidents/INC-4530.md` records what the
service does then.

**4.4** The same bucket is used for every rollout in an evaluation.

## 5. Prerequisite cycles

**5.1** A prerequisite chain that re-enters a flag already being evaluated for
the same user is a configuration fault; the service refuses to serve a targeted
value. The audit records in `docs/incidents/INC-4602.md` show exactly what is
reported, including the case where the cycling flag's `off_variant` happens to
equal the variant its dependant required.

## 6. Definition changes

**6.1** `define` adds a flag. `update` replaces a definition wholesale. `delete`
removes it.

**6.2** The service caches nothing across a definition change: an evaluation
always reflects the definitions as they stand at that moment.

**6.3** Redefining a flag does not change results for evaluations that already
happened.

**6.4** Which bucketing salt is in force across a redefinition is covered by
`docs/CHANGELOG.md` v3.0 / INC-4471. It is not simply the field in the
definition you are looking at, so read that entry before implementing §4.
