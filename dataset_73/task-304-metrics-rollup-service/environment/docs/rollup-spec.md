# Metrics rollup specification

This document specifies how raw samples are rolled into retention tiers. The
tool must reproduce it exactly.

## 1. Series

**1.1** A sample carries a metric `name`, a set of `labels`, a `type`, a
timestamp `t` in whole seconds, and a value.

**1.2** A series is identified by its name together with its labels. Label order
in the capture is not significant: two samples with the same labels in a
different order are the same series.

**1.3** A series key is rendered as the name, then for each label in ascending
key order `,key=value`. A series with no labels renders as just the name.

**1.4** All samples of one series share a type. A series never changes type
within a capture.

## 2. Windows

**2.1** A tier has a name and a window length in seconds. Tiers are listed
shortest first.

**2.2** A sample at time `t` falls in the window starting at
`floor(t / seconds) * seconds`.

**2.3** Windows are half-open: a sample exactly on a boundary belongs to the
window that **starts** there, not the one that ends there.

**2.4** A window with no samples produces no row. Rows are never emitted for
empty windows.

## 3. The first tier

The first tier is computed from the raw samples. Within a window, samples of a
series are taken in ascending `t`; two samples of one series never share a `t`.

### 3.1 Counters

A counter is cumulative, so a window reports the **increase** across it, not the
values themselves.

**3.1.1** The baseline for a window is the last counter value the series had in
any **earlier** window. If the series has no earlier sample, the baseline is the
first sample in this window and that first sample contributes nothing.

**3.1.2** Walking the window in time order, each sample contributes
`value - previous` when `value >= previous`, and contributes `value` when
`value < previous`, which is a counter reset.

**3.1.3** The row reports `delta`, the total of those contributions.

### 3.2 Gauges

**3.2.1** The row reports `min`, `max`, `last`, `count` and `sum` over the
window, and `avg`.

**3.2.2** `avg` is `sum / count` rounded to the nearest integer, with exact
halves rounded to the **even** neighbour. So 5/2 is 2, 7/2 is 4, and -5/2 is -2.

### 3.3 Histograms

**3.3.1** A histogram sample carries `boundaries`, ascending, and `counts`, one
per boundary. Both are integers.

**3.3.2** All samples of a series must carry identical `boundaries`. If any
sample disagrees, the series produces the error `BUCKET_MISMATCH` naming the
series key, and the series contributes no rows at any tier.

**3.3.3** The row reports `boundaries` and `counts`, the element-wise total over
the window.

## 4. Later tiers

**4.1** Every tier after the first is computed from the rows of the tier
immediately below it, never from the raw samples again.

**4.2** A row of the lower tier falls into the higher tier's window by its own
window start, under rule 2.2.

**4.3** Counters: `delta` is the total of the lower rows' deltas.

**4.4** Gauges: `min` is the least of the `min`s, `max` the greatest of the
`max`es, `last` the `last` of the lower row with the greatest window start,
`count` the total of the `count`s, `sum` the total of the `sum`s, and `avg` is
recomputed from that `sum` and `count` under rule 3.2.2. It is never the mean of
the lower `avg`s.

**4.5** Histograms: `counts` are summed element-wise. Boundaries have already
been checked at the first tier.

## 5. Report

**5.1** `rows` lists every row of every tier. Rows are ordered by tier, in the
order the tiers were configured; then by series key, ascending; then by window
start, ascending.

**5.2** A row has `tier`, `series`, `type`, `window`, and the fields its type
defines: `delta` for a counter; `min`, `max`, `last`, `count`, `sum` and `avg`
for a gauge; `boundaries` and `counts` for a histogram.

**5.3** `errors` lists each error once, ordered by series key, with `code` and
`series`.
