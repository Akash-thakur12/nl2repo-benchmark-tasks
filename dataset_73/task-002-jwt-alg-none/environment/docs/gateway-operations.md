# Edge JWT gateway — operations notes

Maintained by the edge platform on-call. This is a runbook and an incident
log, not a specification. Where it disagrees with anything, the recorded
production behaviour in `samples/gateway_corpus.jsonl` wins.

---

## 1. What the gateway is for

Every request into the edge carries a compact JWT that the gateway minted.
The gateway is the only thing that mints and the only thing that verifies, so
the two halves have to stay in step across key rotations, config pushes and
the occasional rollback.

Two attack classes are the reason this component exists at all rather than
being a two-line call into a library:

* **the unsigned algorithm.** A header that names it is refused outright,
  before we look at anything else. We have seen it arrive spelled every way a
  fuzzer can spell it, so the comparison is not a naive equality test — see
  the `alg-none-*` lines of the corpus for the exact set we have caught.
* **algorithm confusion.** A header naming a *different* signing algorithm to
  the one we have pinned is refused too, and it is logged under its own reason
  code so that the weekly security report can count attempts. Note that this
  is a match against a registered algorithm name from RFC 7515 §4.1.1, and
  registered names are case-sensitive tokens — `hs256` is not `HS256`, it is
  simply not a name we pin. The distinction matters: it is the difference
  between "someone is probing us" and "someone fat-fingered a client".

`config/algorithms.json` is the authority on which names we are willing to
pin at all, and on what each name commits us to. When the pin changes, both
the header we stamp and the MAC we compute have to follow it; a token whose
header advertises one algorithm and whose signature was produced with another
is worthless as a credential.

---

## 2. The keyring

Until 2023 the gateway held a single secret in `config["key"]`. That is still
supported and is what the integration test fleet uses. Production has run a
keyring since the November rotation: `config["keyring"]`, a list of entries

```json
{"kid": "k2", "secret": "...", "activated": 1703462400, "retired": 1706745600}
```

`retired` is `null` for an entry that is still live. When a keyring is
present it is the whole story — the standalone `config["key"]` is not
consulted at all, not even as a fallback.

**The ring file is append-only.** Entries are appended in the order the
rotation ticket was closed, which is emphatically not the order the keys came
into force: back-dated entries have been appended after entries that activate
later, and nobody has ever gone back to tidy it. Do not read anything into
list position.

**A kid can appear more than once.** See §4.

### 2.1 Minting

At mint time there is exactly one right answer: the entry that most recently
came into force and has not been retired yet. During a rotation overlap
(§2.2) two entries are simultaneously un-retired; the newer of the two is the
one that mints. If nothing on the ring is in force, minting fails loudly
rather than falling back to anything — we would rather return 500 than issue a
credential nobody can check.

### 2.2 Rotation, and why the windows overlap

The rotation procedure is deliberately not a hard cutover:

1. append the new kid with `activated` set a week ahead of the cutover;
2. at the cutover, set `retired` on the outgoing kid.

That leaves a week during which both entries are un-retired. It exists so
that a stale edge node that has not picked up the new ring yet is still
minting something we can verify. So the windows on the ring **do not
partition the timeline** — at some instants two entries are both in force, and
only the `kid` in the header says which one actually signed.

### 2.3 Verifying

This is the part people get wrong when they rebuild this component, so it is
worth being blunt about it.

We retire k1 at 00:00 on the 1st. A token minted at 23:30 on the 31st has an
hour of life left and it is a perfectly good token; the customer holding it
did nothing wrong and we are not going to sign them out because we rotated a
key. It stays good for its full hour. Equally: k1 was retired months ago, and
if a k1 secret ever leaks, an attacker minting a *fresh* token with `kid: k1`
must not get in. Both of those are true at the same time, and the only thing
that separates them is *when the token says it was minted*.

So the `kid` picks the candidate entries, and the token's own `iat` decides
which of them — if any — was actually entitled to sign it. A `kid` we have
never heard of and a `kid` that was not entitled at that moment are different
failures and are logged under different reason codes; see
`config/reason_codes.md`.

---

## 3. Clock skew

The edge fleet is NTP-disciplined and we alert if any node drifts past
**±60 seconds**. That tolerance is real and we have to live with it: a node
whose clock is a minute slow will happily stamp an `iat` slightly *before* the
activation instant of the very key it just minted with, and those tokens are
legitimate. INC-2231 (the post-rotation outage of 2024-02-08) was exactly
this: a strict comparison against the activation instant, a fleet skewed the
wrong way, and about four minutes of 401s for perfectly good credentials.

> **Hazard — do not "clean this up".** The obvious tidy-up after INC-2231 is
> to hoist the tolerance into one constant and apply it to every timestamp
> comparison in `verify`. Do not. Tolerating skew on a key window costs us
> nothing: the key really was in force and the signature really does check
> out. Tolerating skew on `exp` is a *lifetime extension* — every expired
> token in the world gets another minute of validity, including the ones an
> attacker is replaying. The tolerance belongs to the rotation windows and
> nowhere else. `exp` is compared against our own clock, flat, no grace.

The corpus carries boundary lines on both sides of every one of these
comparisons; they are there precisely so the constant and the inclusivity of
each end can be read off rather than guessed.

---

## 4. Incident log (abridged)

**2023-12-25 — rotation k1 → k2.** k2 appended with `activated` a week
before the cutover, per §2.2. Overlap ran to 2024-01-01, when k1 was retired.

**2024-02-01 — INC-2198, rotation k2 → k1 (rollback).** The scheduled
rotation to a new kid was pushed with a truncated secret and the whole edge
started failing signature checks. Ops rolled it back the fastest way
available: retired k2 and **re-activated k1**, the last key known good. So k1
now owns two disjoint stretches of the timeline, one either side of a month it
did not own, with the same secret in both. This is legal and the ring is
correct as written.

It also broke a downstream analytics job that had loaded the ring into a
dictionary keyed by `kid`. That collapsed k1's two entries into one, and
depending on which way the loop ran it either lost the November window or lost
the February one — half the fleet's tokens went unexplained for a day. The
ring is a *list* and has to stay one.

**2024-02-08 — INC-2231.** Post-rotation 401 storm; see §3.

**2024-02-14 — INC-2240, bad config push.** A push set the pinned algorithm
to `RS256`, which is not something this gateway can do — we are HMAC only, and
`algorithms.json` says so. The gateway at the time treated an unrecognised pin
as fatal and every node in the region refused to start. The fix, and current
behaviour, is that a pin naming an algorithm outside `pinnable` is **ignored**:
the previous pin stays in force, no exception is raised, and everything else in
the same `configure` call (the key, notably) is still applied. A config push
that names an algorithm we cannot do is an operator mistake we log and survive,
not an outage.

---

## 5. Reading the corpus

`samples/gateway_corpus.jsonl` is one JSON object per line, captured from the
auth log and replayed through the gateway to record the verdict:

| field              | meaning                                                            |
| ------------------ | ------------------------------------------------------------------ |
| `id`               | stable label for the line                                            |
| `op`               | `"verify"` or `"issue"`                                              |
| `note`             | what the line is demonstrating                                       |
| `state`            | the gateway state at the time — see below                            |
| `token`            | (verify) the exact token presented; (issue) the exact token produced |
| `payload`, `ttl`   | (issue) the arguments the caller passed                              |
| `header`           | (issue) the header that was stamped                                  |
| `verdict`          | `"ok"`, `"unauthorized"` (an `UnauthorizedError`), or `"invalid"` (a `ValidationError`) |
| `code`             | the reason code logged, `null` when the verdict is `ok`              |
| `claims`           | (verify, ok) the claim dict handed back to the caller                |

`state` is what the gateway was holding: `pin` (the pinned algorithm),
`clock` (the exact Unix second the gateway's clock read), and then either
`key` for single-key mode or `keyring` for the ring. A few lines also carry
`configure_calls`, a list of `configure()` option dicts applied in order after
construction. Secrets are shown as ASCII text; the gateway takes them as
bytes and accepts a `str` by encoding it UTF-8.

Every line is self-contained — the token, the state that produced the verdict
and the verdict itself — so any of them can be recomputed by hand with
`hmac` and `hashlib` in about six lines. `tools/decode.py` will split a token
for you.
