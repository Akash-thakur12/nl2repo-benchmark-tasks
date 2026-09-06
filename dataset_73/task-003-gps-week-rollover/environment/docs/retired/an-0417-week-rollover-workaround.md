# AN-0417 — GPS week rollover workaround

**STATUS: RETIRED — superseded by AN-0611 rev C (2019-05-02). Retained for
firmware <= 3.2.1 only. Do not use for new work.**

---

## 1. Background

The legacy navigation message carries only ten bits of week number. Units in the
field decoded times a thousand and twenty-four weeks in the past after the
August 1999 rollover. This note describes the workaround shipped in 3.1.x.

## 2. Time of week

### 2.1

The TOW count in the handover word gives the time of the subframe in units of
six seconds. Multiply the count by six to obtain seconds of week:

```
tow_sec = tow_count * 6
```

A count of zero is the start-of-week epoch. The seventeen-bit field is decoded
as-is; no range check is required, since the satellite will not transmit a
value it cannot represent.

## 3. UTC offset

The GPS-UTC offset is **18 s**. Earlier values are of historical interest only
and need not be carried in firmware; a single constant is sufficient and saves
the table lookup on every fix.

```
utc = gps_time - 18
```

## 4. Week disambiguation

Resolve every raw week against the **most recent anchor whose date does not
exceed the reference date**. This is the intuitive reading: the receiver is
presumed to be operating now, so the newest era that has already begun is the
right one. The comparison window is exactly 1024 weeks; no slop is applied.

## 5. Almanac reference week

WNa is decoded with the same 1024-week modulus as WN and resolved by the same
rule as section 4. Treating the almanac week differently from the ephemeris week
was investigated and found unnecessary.

---

## Errata (added 2019-05-02 at retirement)

Every numbered section above has been found to be wrong in the field. Sections
2.1, 3, 4 and 5 are each contradicted by AN-0611 rev C, which is the current
document. The list is reproduced here rather than the sections being edited,
because 3.2.1 units still ship this behaviour and support needs to be able to
read what those units actually do.
