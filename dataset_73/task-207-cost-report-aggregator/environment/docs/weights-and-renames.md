# Reconciliation memo: the July shared-cost dispute

**From:** Finance (chargeback desk)
**Date:** 2 August
**Supersedes:** the working assumptions baked into `tools/reconcile_gap.py`

Platform asked us to write down what we actually billed in July, line by line,
because the tool we all had at the time (`tools/reconcile_gap.py`) produced a
different answer and nobody could say which one was the invoice. This memo is
the invoice. Every figure below is what the teams were charged and paid. If a
rewrite of the aggregator does not reproduce these numbers it is wrong,
whatever the old script says.

Two things went wrong in July and they went wrong together.

---

## 1. The split changed in the middle of the month

The shared platform split started July at **3:1 alpha to beta**. On the 12th,
after gamma's workloads moved off, finance amended it to **1:1**. The amendment
was filed as an entry in the export's `weight_changes` list; the export's
`shared_weights` is what was agreed before the month opened.

`reconcile_gap.py` took the amendment and re-split the *whole* month at 1:1.
Alpha's July invoice was therefore too low by about 40 dollars and beta
disputed it. The ruling was that **an amendment bills from the day it was
made**: everything dated before the 12th stays at 3:1, and the 12th itself is
already the new split, because the amendment was effective that morning. We are
not going to reissue invoices for the first eleven days of a month every time a
weight moves.

Note also that the list is in the order the desk **applied** the amendments,
which is not the order of the days they take effect - a late amendment is
sometimes backdated and filed after one that was already in the book. Read the
`day` on each entry; do not read the position in the list. If two entries carry
the same `day`, the one filed later is the correction to the earlier one and is
the one that stands.

### Worked lines (July, shared_weights `{"alpha": 3, "beta": 1}`)

The amendments in force in July, in the order the desk filed them:

| filed | day | weights                     |
|-------|-----|-----------------------------|
| 1st   | 20  | `{"alpha": 0, "beta": 0}`   |
| 2nd   | 12  | `{"alpha": 1, "beta": 1}`   |

The 20th entry was filed first because it had already been agreed at the
quarterly review; the 12th was raised afterwards.

| line | day | cents | split used | alpha | beta | unallocated |
|------|-----|-------|------------|-------|------|-------------|
| J-1  |  5  |  101  | 3:1        |  76   |  25  |    0        |
| J-2  | 12  |  101  | 1:1        |  51   |  50  |    0        |
| J-3  | 15  |  101  | 1:1        |  51   |  50  |    0        |
| J-4  | 20  |  101  | none       |   0   |   0  |  101        |

J-1 is before the first amendment, so it uses the opening `shared_weights`.
J-2 falls on the amendment day itself. J-3 is after it. J-4 is on and after the
20th, where the platform contract lapsed and both weights went to zero; with
nothing to split across, the whole line was carried as unallocated and written
off centrally.

Two arithmetic checks, because these are the numbers that settle it:

* 101 at 3:1 is 75 and 25, one cent short; the extra cent goes to the heavier
  weight, so 76 and 25. That is J-1.
* 101 at 1:1 is 50 and 50, one cent short; the extra cent goes to the
  alphabetically first team of the tie, so 51 and 50. That is J-2 and J-3.

The old script's answer for the four lines together was 204/102 with nothing
unallocated. Ours is 178/125 with 101 unallocated. The difference is the whole
dispute.

---

## 2. Two teams were renamed and the collector never noticed

`bravo` became `beta` when the two groups merged in June, and `aardvark` became
`zeta` when it moved under the data org. The collector still stamps the retired
names on lines, and the weight table we hand it still has a row filed under the
old name, because nobody owns that config. Exports carry a `renamed_from` map
recording the retirements; it is the only place the correspondence is written
down.

A retired name is **the same team**. It is not an unknown team, it is not an
error, and the money on such a line is not dropped - it is billed to the
successor and shows up on the successor's invoice. We were quite clear about
this with platform after the second dispute: beta was billed for bravo's
reservation and paid it.

The same goes for the weight table. A weight filed under a retired name is that
team's weight and it **counts**. If the successor also has a row of its own,
the two are added together. That is the opposite of what happens to a weight
naming a team the report does not cover at all, which is simply struck out and
does not count toward the total.

### Worked lines

**R-1** - usage, 4000c, tagged `bravo`. Billed to **beta**: beta usage 4000, no
exception raised.

**R-2** - shared, 101c, weight table `{"alpha": 1, "bravo": 2, "beta": 1}`.
Bravo's 2 folds into beta's 1, so the split is alpha 1 against beta 3, total 4.
101 at 1:3 is 25 and 75, one cent short; the heavier weight takes it.
**alpha 25, beta 76.** (Striking bravo's row out instead would have given a
1:1 split and 51/50, which is what the old script printed and what beta
queried.)

**R-3** - shared, 3c, weight table `{"aardvark": 1, "alpha": 1}`, report
covering alpha and zeta. Aardvark's row is zeta's. Both weights are 1, so both
get 1c and one cent is left; the tie is broken on the name we bill under, not
the retired spelling, so it goes to **alpha**. **alpha 2, zeta 1.** Sorting on
the row keys as written would have put aardvark first and paid zeta 2 - it did
not.

**R-4** - usage, 250c, tagged `omega`. Omega was retired into `delta`, and
delta is not one of the teams this report covers, so there is nothing to bill.
This one *is* an exception, and it is raised against the name the line carries
- `omega`, not `delta`, because `omega` is what an engineer looking at the
export will search for. The 250c was not charged to anybody.

---

## 3. What this means for the rewrite

* The split applied to a shared line is the one in force on that line's own
  day, taken from the latest-dated amendment on or before it, falling back to
  `shared_weights` when there is none. Later filing wins a shared day.
* An amendment dated after the period end never bills; one dated before the
  period opens bills from the first line onward.
* A retired name resolves to its successor everywhere it can appear - on usage,
  reservation and credit lines, and as a key in `shared_weights` and in a
  `weight_changes` entry.
* A resolved weight is added to the successor's; an unresolvable name is an
  exception on lines and a struck-out row in the weight table.
* Nothing above changes amortisation. The reservation remainder still lands on
  the earliest days of the term, as section 4.2 of the specification has always
  said, whatever the header comment on the old script claims.
