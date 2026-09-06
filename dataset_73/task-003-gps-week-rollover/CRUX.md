# Cruxes — task-003-gps-week-rollover

Reviewer note. For each crux: the wrong default it punishes, the evidence in
`environment/` that makes the right answer uniquely recoverable, and the tests
that catch it.

The claim being made is **not** "this task is hard because something is
under-specified". Every rule and every constant below is stated exactly once, in
an authoritative artifact that ships inside `environment/`. What has been removed
is the *restatement of those rules inside `instruction.md`*, which previously
handed over the complete algorithm as an executable formula.

Run `python tools/check_crux.py` for the mechanical proof: it builds four
single-crux wrong-default engines plus the combined "skimmer" engine and runs the
real suite against each.

```
baseline: reference engine 97/97

crux-C  most-recent anchor, no grace        86/97   score 0.887
crux-E  tow_count * 6, no range check       46/97   score 0.474
crux-I  fixed 18 s GPS-UTC offset           71/97   score 0.732
crux-H  WNa modulo 1024 via the era rule    90/97   score 0.928
skimmer all four AN-0417 readings           31/97   score 0.320
```

The skimmer is the calibration case: an implementer who reads `instruction.md`,
runs `environment/tools/rollover_diag.py`, and believes its ROOT CAUSE line
scores 0.333 — honestly partial, and below the 0.5 pass threshold.

---

## E — HOW TOW count names the *next* subframe, so `tow_count = 0` is the *end* of the week

**Wrong default.** `tow_sec = tow_count * 6`, treating the count as this
subframe's own time, and accepting the full 17-bit range 0..131071.

**Correct.** ICD-GPS-200 20.3.3.2 defines the TOW count as the time of the
leading edge of the **next** subframe, and 20.3.3.3.1.1 defines WN as the week of
the subframe actually being transmitted. The current subframe therefore starts
six seconds earlier, and `tow_count = 0` identifies the **last** subframe of week
WN at second 604794 — the counter wraps while the week field does not advance, so
the decoded time jumps backwards seven days relative to the naive reading. The
legal range is 0..100799 (604800/6), not 0..131071.

No CURRENT artifact states the six-second subframe length as a number: AN-0611 s2
says to derive it, and the only place the numeral appears is the RETIRED AN-0417
s2.1, inside the sentence that gets the semantics wrong. It has to be derived from
"each subframe consists of 300 bits, transmitted at 50 bits per second"
(ICD 20.3.2) -- the ICD's own 0..100,799 range (604800/6) corroborates it -- and
can then be confirmed against two adjacent corpus rows.

**Evidence in `environment/`**
- `docs/icd-200-extracts.md` — the HOW paragraph, the WN paragraph, the 300-bit /
  50-bps paragraph, and the stated 0..100,799 range.
- `docs/an-0611-time-decoding.md` §6.1 — the integration note: *"A TOW count of
  zero identifies the final subframe of week WN, not the first."*
- `samples/decoded_frames.jsonl` — F002 is a `tow_count = 0` row, F003/F004 are
  adjacent subframes six seconds apart; the rule is provable from shipped data
  before any test runs.
- **Misdirection:** `docs/retired/an-0417-week-rollover-workaround.md` §2.1 and a
  stale comment above `to_utc` in the environment stub both assert `tow_count * 6`.

**Divergence.** ref 2026-01-01, lnav raw week 282 (full week 1306):
`tow_count = 0` → **2024-09-07 23:59:36** vs naive 2024-08-31 23:59:42 — seven
days, a different month. `from_utc(2024-08-31 23:59:42)` → **(1306, 1)**; the
naive inverse gives (1305, 100797) — wrong week *and* wrong count.

**Caught by** `test_tow_count_names_the_next_subframe`,
`test_tow_count_zero_is_the_last_subframe_of_the_week`,
`test_adjacent_subframes_are_six_seconds_apart`,
`test_tow_count_range_is_narrower_than_the_field`,
`test_tow_day_boundary_lands_before_midnight`,
`test_from_utc_returns_the_next_subframe_count`,
`test_to_utc_from_utc_round_trip`, plus both corpus replays.

---

## I — The GPS-UTC offset in force *at the decoded instant*

**Wrong default.** Use 18 s everywhere (the current value), or use the offset in
force at `config["ref"]`.

**Correct.** `to_utc` subtracts the offset in force at the GPS instant being
decoded; `from_utc` adds back the offset in force at the UTC instant being
converted. `data/leap_seconds.tab` ships the real 19-row IERS TAI-UTC history
(1980-01-01 = 19 through 2017-01-01 = 37). `GPS-UTC = TAI-UTC - 19`, forced by the
table header: GPS time was coincident with UTC at the GPS epoch 1980-01-06, when
TAI-UTC was 19 s.

The table carries **two** effective-date columns because the same leap step
happens at two different instants on the two scales. The forward path compares
against `gps_effective`; the inverse path compares against `utc_effective`.
Choosing the wrong column is a clean one-second error, and only inside a window a
few seconds wide — which is exactly why it survives casual testing.

**Evidence in `environment/`**
- `data/leap_seconds.tab` — complete, with both effective columns and the header
  that fixes the −19 constant.
- `docs/an-0611-time-decoding.md` §6.2 — *"the offset applied shall be the one in
  force at the instant being decoded"*, and which column each direction uses.
- **Misdirection:** AN-0417 §3 says the opposite (*"The GPS-UTC offset is 18 s;
  earlier values are of historical interest only"*); `samples/receiver_boot.log`
  carries a WARN blaming a stale leap table, and a ticket that chases it.
  Resolvable, not ambiguous: AN-0611 §7 lists that warning as a known false
  alarm, because no leap second has been announced since 2017-01-01.

**Divergence.** cnav week 199, tow 1 → **2003-06-14 23:59:47** (offset 13); "18
everywhere" gives 23:59:42 and no leap correction gives 2003-06-15 00:00:00 — a
different date. cnav week 906, tow 1 → **2016-12-31 23:59:43** using
`gps_effective`; using `utc_effective` on the forward path gives 23:59:42.
Because a 6-second TOW quantum puts 13 and 18 in the same day bucket, these are
asserted as exact datetimes, not dates.

**Caught by** `test_leap_offset_uses_the_value_in_force_at_the_instant`,
`test_leap_offset_picks_the_right_effective_column`,
`test_leap_offset_before_the_first_tabulated_row_is_zero`,
`test_leap_offset_rejects_an_unknown_scale`,
`test_decoded_instant_uses_the_historical_offset`,
`test_decoded_instant_at_the_2017_leap_boundary`,
`test_from_utc_uses_the_utc_effective_column`, plus both corpus replays.

---

## H — Four week fields with four widths, and the 8-bit almanac week pivots on the record's own ephemeris week

**Wrong defaults** — three of them, each isolated on a *different* test row so
partial credit stays continuous (ref 2026-01-01, ref week 1375):

| wrong reading | row | correct | wrong |
|---|---|---|---|
| (a) treat WNa as 10-bit and run the era rule | eph 1306, WNa 100 | **1380** | 1124 |
| (b) pivot on the reference date, not the record's week | eph 1140, WNa 100 | **1124** | 1380 |
| (c) floor to the most recent congruent week in the past | eph 1306, WNa 100 | **1380** | 1124 |

(a) and (c) agree on row (b), and (b) agrees on row (a), so no single test carries
all three. Tie case: pivot 1375, WNa 223 → **1247**, not 1503.

**Correct.** Four sources, described in `data/constellations.csv`: `lnav` 10-bit
truncated (era rule); `cnav` 13-bit absolute, **no** disambiguation; `almanac`
WNa 8-bit, modulo 256; `bdt` 13-bit absolute against its own epoch 2006-01-01 and
running 14 s behind GPS.

The coupling is the almanac. Decoding one almanac record chains four rules — era
rule against `ref` → ephemeris week → nearest-congruent-mod-256 pivot on **that**
week → TOW semantics → leap lookup on the resulting instant — and an error in any
earlier link moves the answer by years. Separately, era resolution happens in GPS
time *before* the leap subtraction, so the corrected UTC can land in the previous
week without the resolved week changing.

**Evidence in `environment/`**
- `data/constellations.csv` — `week_bits`, `absolute`, `week_epoch`,
  `seconds_behind_gps`, `pivot` for all four sources.
- `docs/icd-200-extracts.md` — the WNa paragraph (*"modulo 256 of the GPS week"*)
  and the WN paragraph (*"the week number of the subframe in which it is
  transmitted"*); the pair is what forces the pivot to be the record's own week.
- `docs/an-0611-time-decoding.md` §5 — the nearest-congruent rule **and** the
  tie-break, stated explicitly, so exactly one answer exists.
- `samples/decoded_frames.jsonl` — the one almanac row shipped (F012/F022) is
  deliberately chosen where flooring, nearest-to-eph and nearest-to-ref all agree,
  so the samples confirm the modulus without giving away the pivot direction. The
  held-out rows attack that separation.
- `samples/receiver_boot.log` — the ERROR lines show an almanac reference week
  resolving 182 weeks from the ephemeris week that carried it.
- **Misdirection:** AN-0417 §5 (*"WNa is decoded with the same 1024-week modulus…
  Treating the almanac week differently was investigated and found
  unnecessary"*).

**Caught by** `test_cnav_week_is_absolute`,
`test_almanac_pivots_forward_on_its_own_ephemeris_week`,
`test_almanac_pivots_backward_on_an_older_ephemeris_week`,
`test_almanac_tie_resolves_to_the_earlier_week`,
`test_almanac_requires_the_carrying_week`,
`test_bdt_uses_its_own_epoch_and_scale_offset`,
`test_raw_week_must_fit_the_field_width`, `test_unknown_source_is_rejected`,
`test_almanac_decode_chains_every_rule`, plus the holdout replay (H010–H015).

---

## C — A retired app note, a diagnostic tool and a boot log all name the wrong root cause

**Wrong default.** *"Resolve every raw week against the most recent anchor whose
date does not exceed the reference date"* — which sounds obviously right, and is
what the shipped diagnostic recommends in capital letters.

**Correct.** The rule is the **first (oldest)** qualifying era, within
1024 weeks **plus 30 days** of the reference date, with era 0 as an unconditional
fallback. This behaviour is unchanged from the original reference implementation,
so all nine pre-existing test functions still pass untouched; what changed is that
the rule is no longer written down in `instruction.md`, and the environment now
actively argues against it.

**Four artifacts on disk point at the wrong answer, each refutable:**

1. `environment/tools/rollover_diag.py` — a runnable stdlib field diagnostic. It
   reads the sample corpus, implements most-recent-anchor + `tow*6` + fixed 18 s +
   WNa mod 1024, **reproduces 18 of the 24 sample rows exactly**, prints
   `ROOT CAUSE (AN-0417 s4): …` — and then prints
   `6 frames unexplained -- see AN-0611`. It is credible precisely because it is
   mostly right, and it is self-refuting because it reports its own failure count
   and names its successor.
2. `environment/docs/retired/an-0417-week-rollover-workaround.md` — headed
   **"STATUS: RETIRED — superseded by AN-0611 rev C (2019-05-02). Retained for
   firmware <= 3.2.1 only."** on line 1, asserting all four wrong readings.
3. A stale comment above `to_utc` in `environment/engine/engine.py`:
   `# tow_count is seconds-of-week / 6 for this subframe (AN-0417 s2.1)`.
4. `environment/samples/receiver_boot.log` — a WARN blames a stale leap table
   while the ERROR lines two below show the actual defect. AN-0611 §7 lists that
   WARN as a known false alarm.

**Evidence for the right answer.** `docs/an-0611-time-decoding.md` §3 states it in
prose: *"Candidate dates are tested in ascending order of era base week. The first
candidate that is not later than the reference date, and not more than 1024 weeks
plus 30 days before it, is accepted. If no candidate qualifies, era 0 is used
unconditionally."* `data/epoch_anchors.csv` carries the anchors and states that
day 0 of a GPS week is a Sunday.

**Divergence.** ref 2026-01-01, raw week 351: era 0 lands on 2006-05-14, 7172 days
before ref — inside the 30-day grace (7168 < 7172 <= 7198) — so era 0 wins. Both
the most-recent-anchor reading and the no-grace reading answer 2025-12-28, twenty
years out. The grace is load-bearing elsewhere too: raw 0 with ref 2019-04-14 must
give 1999-08-22, but `1024*7` exactly gives 2019-04-07.

**Caught by** `test_era_candidates_tested_in_ascending_order`,
`test_era_grace_of_thirty_days_is_part_of_the_rule`,
`test_era_boundary_is_sharp_at_the_grace_edge`,
`test_era_candidate_includes_the_requested_day_of_week`,
`test_era_fallback_when_no_anchor_qualifies`, the five original anchor tests, and
both corpus replays.

---

## Solvability

Every constant and rule lives in `environment/` exactly once, in an authoritative
artifact:

| what | where |
|---|---|
| era anchors | `data/epoch_anchors.csv` |
| field widths, epochs, scale offsets, pivots | `data/constellations.csv` |
| leap history, both effective columns | `data/leap_seconds.tab` |
| the four behavioural rules | `docs/an-0611-time-decoding.md` rev C |
| the ICD paragraphs they rest on | `docs/icd-200-extracts.md` |

Every contradicting artifact is stamped stale on its face (AN-0417 carries the
RETIRED header naming its successor on line 1; the diagnostic prints its own
unexplained-frame count and defers to AN-0611; the boot-log warning is listed
under AN-0611's known false alarms). The three edges that look underdetermined —
the WNa tie at exactly ±128 weeks, which effective-date column each direction
uses, and the 0..100799 TOW range — are each pinned by one explicit sentence.
Nothing rests on taste.

The only genuine inference hop is deriving the 6-second subframe length from
"300 bits at 50 bits per second"; it is independently confirmable against the
ICD's stated 0..100,799 count range and against two adjacent rows of the shipped
corpus.

## Reward continuity

97 collected cases across 40 test functions, layered:

| layer | functions | what it earns |
|---|---|---|
| L0 | 9 (byte-identical to the originals) | the date API and validation |
| L1 | 5 | era ordering, the 30-day grace, the dow-bearing candidate, the fallback |
| L2 | 6 | the leap history and the two effective columns |
| L3 | 5 | TOW semantics and range validation |
| L4 | 9 | the four sources and the WNa pivot |
| L5 | 4 | the inverse conversion and round-trips |
| L6 | 2 parametrized | sample replay (24) and holdout replay (15) |

A model that gets only the era rule right still scores; one that also gets the
leap table right scores more; the almanac pivot and the TOW wrap are separately
earnable. No test is all-or-nothing.
