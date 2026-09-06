# Site registry: operations note

Facilities keeps the register of offices and their grid coordinates; Security
keeps the travel policy in the same register. Both are exported into every
capture. This note is normative for how an entry is read.

## Why entries have dates on them

Offices move. When the Rotterdam harbour team took the new building in April,
the site kept its name and changed its coordinates, and every sign-in from
before the move is still a sign-in from the old building. If the exporter
measured those against the new coordinates it would report a 20 km jump that
never happened, and the on-call rota would spend a morning on it.

So the register does not hold a site's coordinates. It holds the coordinates it
has had, each stamped with the moment they came into force.

## How an entry is read

A `locations` entry is one of two shapes.

- A plain object, `{"x": 0, "y": 0}`. The site has never moved and those are
  its coordinates for every event in the capture.
- A list of revisions, each `{"from_t": ..., "x": ..., "y": ...}`.

For a list, four rules decide which revision applies to a given moment.

1. **The one in force is the latest revision whose `from_t` is not after the
   moment being measured.**
2. **`from_t` is inclusive.** A revision filed with `from_t` 400000 is in force
   for an event at exactly t=400000, not from the next second.
3. **A revision stays in force until the next one begins.** There is no expiry
   field; the next revision ends the previous one.
4. **A moment earlier than the oldest revision uses the oldest revision.** When
   the register was first imported every site was backfilled with the
   coordinates it had at the time, so the oldest revision reaches back to the
   start of the log. There is no such thing as a site with no coordinates.

**Entries appear in the order they were filed, which is not chronological.**
The export groups revisions by the person who filed the change and orders each
group however that team works - some file newest first, some oldest first, and
one team's export has never been in any order at all. Do not assume the first
or the last element of the list is the one you want. Read the `from_t` values.

## The moment being measured

The moment is the timestamp of the event whose location you are resolving, not
the timestamp of the capture, the run, or the other end of a journey. A journey
between two sign-ins therefore has two moments: the earlier sign-in's site is
resolved as of the earlier sign-in, and the later sign-in's site as of the later
sign-in. The same pair of site names can be a different number of kilometres
apart in January and in April, and that is the intended behaviour.

## The travel policy

The register also carries the travel policy, and it is resolved in exactly the
same way, by the four rules above.

When a capture carries a `speed_policy` list, each entry is
`{"from_t": ..., "kmh": ...}` and it is resolved **against the time of the
sign-in under review**, which is the later of the two sign-ins being compared.
The limit that governs an alert is the limit that was published when the
sign-in happened, so that an export re-run next year still says what Security
signed off on this year.

When a capture carries no `speed_policy`, the flat `max_speed_kmh` field is the
limit. That field is still written into every capture for the benefit of older
readers, and it is **not** kept in step with the policy: where a policy is
present, the policy governs and `max_speed_kmh` is a leftover.
