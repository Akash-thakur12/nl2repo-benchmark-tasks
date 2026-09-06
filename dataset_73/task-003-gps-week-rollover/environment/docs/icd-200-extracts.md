# ICD-GPS-200 — extracts held for firmware reference

Verbatim extracts from the interface control document, retained because the full
document is not redistributable. Paragraph numbering follows the source.

---

## 20.3.2 Message structure

Each frame of the navigation message consists of five subframes. **Each subframe
consists of 300 bits, transmitted at 50 bits per second.** Subframes are
transmitted in numerical order and the frame repeats every 30 seconds.

---

## 20.3.3.2 Handover Word (HOW)

Bits 1 through 17 of the HOW shall contain the **time-of-week (TOW) count**.

> The TOW count is a truncated version of the full time-of-week count. It
> consists of the 17 most significant bits of the 19-bit time-of-week count, and
> therefore advances in units of one subframe. **The TOW count represents the
> time of the leading edge of the next subframe**, expressed in units of one
> subframe from the start of the current week.

> The count is set to zero at the start-of-week epoch and advances by one at each
> subframe boundary thereafter; **the count ranges from 0 through 100,799**, and
> is reset to zero at the following start-of-week epoch.

*Engineering note kept with this extract:* a 17-bit field can hold values up to
131,071. Values above the stated range are not produced by a healthy satellite
and shall be rejected by the receiver rather than decoded.

---

## 20.3.3.3.1.1 Week Number (WN)

Bits 1 through 10 of word 3 of subframe 1 shall contain the ten least
significant bits of the full week number. **WN is the week number of the
subframe in which it is transmitted**, and is incremented at each start-of-week
epoch. The user must account for the truncation to ten bits; the full week
number is not transmitted in the legacy message.

---

## 20.3.3.5.1.5 Almanac Reference Week (WNa)

Bits 1 through 8 of word 3 of subframe 5, page 25, shall contain **WNa, which
shall be modulo 256 of the GPS week number** to which the almanac reference time
`toa` applies.

WNa is a property of the almanac data set, not of the subframe that carries it,
and a satellite may continue to broadcast an almanac whose reference week lies
either side of the current week.

---

## 30.3.3 CNAV message

The CNAV message week number field is **thirteen bits wide** and carries the
week number without truncation; no user disambiguation is required.
