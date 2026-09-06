# notes on the sample captures

Scratch pad, not a spec. I wrote these while pulling the captures together in
January; `docs/` is the thing that's actually normative and it wins wherever I
have got something wrong here.

---

**2025-01-08** - grabbed six sessions off the staging runner. Picked boring ones
on purpose: single-digit versions, applied in order, everything reversible,
nothing failed, nobody was holding the lock. Good for smoke-testing, useless for
anything interesting.

**2025-01-09** - checked expected.json against the runner twice, once from a
clean checkout. Matches.

**2025-01-09** - worked out the checksum thing. It's just sha256 of `up` and
`down` glued together exactly as captured, nothing clever:

```
$ printf 'UP 1DOWN 1' | sha256sum
d4da24148186c478e6e995a287e9b5a630ee507fb2523a9cdb0777e88fa76a25
```

which is what s01's V1 hashes to. So DRIFT just means the file is not
byte-for-byte what it was when it ran - a re-indent, a stray trailing space, a
checkout with different line endings, any of it counts as drift. Slightly
brutal but at least it's simple, and it explains the two incidents.

**2025-01-14** - reminder to self, because I got this wrong on the first pass:
the applied list is one flat sequence across the *whole* session, not one list
per command, and rollbacks go in it too with `"direction": "down"`. Errors are
the ones keyed by command index, not the applied list.

**2025-02-02** - somebody asked why `up` with no `steps` in s05 runs everything.
Because that's the default. `down` with no `steps` is one. They are not
symmetric and I don't love it, but it's what the runner does and section 4 says
so.

**2025-03-20** - added s07 after the March incident, so there's at least one
sample with a `baseline` record in it. It is a deliberately dull one: nothing is
applied and the only migration defined is above the new floor, so it does not
demonstrate anything except that the record exists and does not blow the tool
up. The interesting one is written up in `docs/incident-2025-03-14.md`.

**TODO** - re-read `docs/runner-spec.md` 1.3 properly at some point. There is a
digest table in this directory that I have not looked at.
