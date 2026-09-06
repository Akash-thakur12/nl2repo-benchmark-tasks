# AN-0611 rev C — Broadcast time decoding

**Status: CURRENT.** Supersedes AN-0417 (*GPS week rollover workaround*) in
full. Rev C issued 2019-05-02 after the second rollover.

Applies to all firmware from 3.3.0. Anything in AN-0417 that contradicts this
note is wrong; AN-0417 is retained on disk only for units still on 3.2.1.

---

## 1. Scope

This note specifies how the decoder turns the broadcast week and time-of-week
fields into an absolute UTC instant, and how it goes back the other way. The
numeric tables it refers to are shipped alongside it:

| what | where |
|---|---|
| era anchors | `data/epoch_anchors.csv` |
| week-field widths, epochs, scale offsets | `data/constellations.csv` |
| TAI-UTC history | `data/leap_seconds.tab` |
| ICD paragraphs quoted below | `docs/icd-200-extracts.md` |

---

## 2. Subframe length

The decoder never hard-codes a subframe duration as a magic number. It is a
consequence of the message structure in ICD-GPS-200 20.3.2 and is derived once
at build time from the bit count and the data rate given there. Two adjacent
frames in `samples/decoded_frames.jsonl` differ by exactly one subframe and can
be used to confirm the derived value.

---

## 3. Era resolution of a truncated week (LNAV)

A 10-bit week field is resolved against the configured **reference date**.

> Candidate dates are tested in **ascending order of era base week**. The first
> candidate that is not later than the reference date, and not more than 1024
> weeks plus 30 days before it, is accepted. If no candidate qualifies, era 0 is
> used unconditionally.

The candidate for an era is that era's anchor date advanced by the number of
weeks the raw field is past the era base week, modulo 1024, plus the requested
day of week.

Three points are frequently got wrong and are called out deliberately:

* **Ascending, not descending.** The oldest qualifying era wins, not the newest.
  Choosing the most recent anchor whose date does not exceed the reference date
  — the AN-0417 workaround — gives a different answer for a large family of raw
  week values and is not acceptable.
* **The 30-day grace is part of the rule**, not a tolerance. Dropping it moves
  the boundary case by a full era.
* Era resolution happens **in the GPS time scale, before the UTC offset is
  subtracted**. The corrected UTC instant may therefore fall in the calendar
  week before the resolved week; the resolved week does not change because of
  it.

---

## 4. The other three week fields

`data/constellations.csv` is authoritative for widths and epochs.

* **CNAV** — thirteen bits, already absolute. No disambiguation of any kind is
  applied. Passing a CNAV week through the era rule is a defect.
* **BDT (BeiDou D1)** — thirteen bits, absolute, referred to its own epoch, and
  running a constant number of seconds behind GPS time. Decode against the BDT
  epoch, bring the instant onto the GPS scale using the offset in the table, and
  only then apply the UTC correction of section 6.
* **Almanac WNa** — eight bits, see section 5.

---

## 5. Almanac reference week

ICD-GPS-200 20.3.3.5.1.5 defines WNa as modulo **256** of the GPS week; ICD
20.3.3.3.1.1 defines WN as the week of the subframe in which it is transmitted.
Those two sentences together fix the pivot:

> WNa shall be resolved to the week congruent modulo 256 that is **closest to
> the week of the subframe in which it was received**; a tie resolves to the
> earlier week.

That is, the pivot is the record's own resolved **ephemeris week** — the output
of section 3 for the WN field of the same record — and **not** the reference
date, and **not** the most recent congruent week in the past. All three readings
agree on some records and disagree by 256 weeks (about five years) on others,
which is why field units running the AN-0417 logic reported almanacs dated half
a decade away from the ephemeris that carried them.

The chain for one almanac record is therefore: era rule against the reference
date → ephemeris week → nearest-congruent-modulo-256 pivot on that week → TOW
semantics (section 6) → UTC offset lookup on the resulting instant. An error in
any earlier link moves the final answer by years.

---

## 6. Time of week, and the UTC offset

### 6.1 TOW count

Per ICD-GPS-200 20.3.3.2 the HOW TOW count is the time of the leading edge of
the **next** subframe, and WN is the week of the subframe actually being
transmitted. The decoder must place the instant at the start of the subframe it
is decoding, not at the start of the one that follows it.

> **Integration note.** A TOW count of zero identifies the final subframe of
> week WN, not the first; the transmitted week number is not advanced until the
> following subframe. Firmware that reads a zero count as the start of the week
> reports a time seven days early.

The valid range of the count is the one printed in the ICD, which is narrower
than the 17-bit field allows. A count outside that range shall be rejected as a
validation failure, not clamped.

### 6.2 UTC offset

GPS time does not step. UTC does. The difference is tabulated in
`data/leap_seconds.tab`.

> The offset applied shall be **the one in force at the instant being decoded**,
> not the offset currently broadcast and not the offset in force at the
> configured reference date.

The table carries two effective-date columns because the same leap step happens
at two different instants on the two scales:

* the **forward** path (broadcast fields → UTC) has a GPS-scale instant in hand,
  and compares it against `gps_effective`;
* the **inverse** path (UTC → broadcast fields) has a UTC instant in hand, and
  compares it against `utc_effective`.

Using the wrong column is a clean one-second error, and only inside a window a
few seconds wide at each historical leap — which is exactly why it survives
casual testing. The regression corpus pins it at 2017-01-01.

`GPS-UTC = TAI-UTC - 19`; the table's own header states why.

---

## 7. Known false alarms

* `POST: leap table age 3287 d exceeds 1095 d threshold` in the boot log is
  **cosmetic**. No leap second has been announced since 2017-01-01, so a table
  whose newest row is that date is current, not stale. Do not treat this warning
  as the cause of a decoding discrepancy; several field reports have chased it
  and found nothing.
* `rollover_diag.py` is a pre-rev-C field tool. Its ROOT CAUSE line reproduces
  the AN-0417 workaround and is retained only because its frame dump is useful.
  It reports its own unexplained-frame count; that count is the AN-0417 logic
  failing, not corrupt data.
