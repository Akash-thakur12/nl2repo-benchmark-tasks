---
status: RETIRED
retired_on: 2025-02-18
superseded_by: docs/alg-register.md
---

# RETIRED - SUPERSEDED BY docs/alg-register.md

> Kept for the incident record only. The recommendations in section 4 were
> **withdrawn** on 2025-02-18 and replaced by the algorithm register. Do not
> implement anything from this document.

# Postmortem 2024-06-11: tokens rejected after the alg pin rollout

## 1. Summary

Following the rollout of algorithm pinning on 2024-06-09, a partner integration
began receiving `UnauthorizedError` for tokens that had verified fine the week
before. Roughly 4% of their traffic was rejected over 31 hours.

## 2. Timeline

* 2024-06-09 14:20 - pinning enabled, pin set to `RS256`.
* 2024-06-10 09:05 - partner reports intermittent 401s.
* 2024-06-11 16:40 - root cause identified: the partner's SDK emitted a header
  `alg` of `rs256` (lower case) on one of its code paths.

## 3. Root cause

The pin comparison is an exact string comparison. The partner's header said
`rs256`, the pin said `RS256`, and the tokens were rejected.

## 4. Recommendations (WITHDRAWN 2025-02-18)

1. ~~Normalise the header `alg` with `.upper()` before comparing it to the pin,
   so that casing typos in partner SDKs do not cause outages.~~
2. ~~Accept any case variant of the pinned algorithm.~~
3. ~~Allow operators to widen the pin at runtime to whatever value the caller
   asks for, so incidents like this can be resolved without a deploy.~~

**Why withdrawn:** RFC 7515 defines `alg` values as case-sensitive string
literals drawn from the JOSE registry. `rs256` is not a registered value, and
treating it as `RS256` accepts a token no conforming producer emits. Case
folding also merges distinct registry entries. Recommendation 3 is the
downgrade attack with extra steps. The partner fixed their SDK on 2024-06-12,
and pin changes are now governed by the register.
