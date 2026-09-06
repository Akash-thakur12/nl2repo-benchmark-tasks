---
title: Incident root-cause classification
owner: platform-sre
status: IN FORCE
version: 2
supersedes: retired/runbook-v1.md
---

# Incident root-cause classification

This runbook specifies how an incident telemetry window is turned into a single
root-cause verdict. It is the in-force document. Anything under `retired/` is
kept for audit only and must not be implemented.

## 1. Building the window

Samples arrive in arrival order, which is not time order, and a timestamp may
be delivered more than once. Reconstruct the window exactly as
`collector-agent.md` §2 requires — collapse duplicate timestamps keeping the
most recently received copy, then order ascending by timestamp — before doing
anything else in this document. Every reference below to "the first sample",
"the last sample" or "consecutive samples" means the reconstructed window, not
the arrival buffer.

The **span** of a window is the timestamp of its last sample minus the
timestamp of its first sample.

## 2. Admissibility

A window that fails either check below is not classified. Report
`INSUFFICIENT_DATA` and stop.

* **At least two distinct timestamps.** A single timestamp — however many
  copies of it were delivered — gives no interval to measure activity over.
* **Span of at least 30 seconds.** Below half a minute the per-minute rates in
  §4 are extrapolated by a factor of more than two from a single scrape
  interval, and the resulting figure is dominated by scrape jitter rather than
  by the host. We have burned enough on-call time on 12-second windows that
  fired the disk cascade on an idle box. A span of exactly 30 seconds is
  admissible; anything shorter is not.

## 3. Which thresholds apply

Thresholds are versioned; see `threshold-policy.md`.

Classification must be **reproducible**. When an incident is re-analysed —
during a post-incident review, when a regression suite replays an old window,
or when someone asks why the pager fired — the verdict must be the verdict the
on-call engineer actually saw at the time, not the verdict today's thresholds
would produce for the same numbers. A classifier that quietly re-judges history
against the current table makes every review argument unresolvable.

Concretely: apply the revision whose `effective_from` is the greatest value
that is not later than the timestamp of the **first sample of the window**. A
window that straddles a revision boundary is judged entirely under the revision
that was in force when it opened; we do not re-thresholds mid-window and we do
not use the revision in force when it closed.

## 4. Deriving the comparands

Two different kinds of threshold appear in the policy table, and they are read
in two different ways.

**Counter-derived metrics** (`disk`, `net`, `gc`). Compute the window total for
the counter using the reset-recovery rule in `collector-agent.md` §3, then
convert it to the per-minute rate the policy table's `_rate_per_min` /
`_ms_per_min` columns are expressed in:

```
rate_per_min = window_total * 60.0 / span_seconds
```

The rate is what is compared against the policy value. A raw
last-minus-first difference is *not* the comparand; it only coincides with the
rate on a window that happens to span exactly 60 seconds.

**Gauge metrics** (`cpu`, `mem`). The comparand is the absolute reading of the
**last** sample in the window. The one exception is the CPU *jump*, which is
the last sample's `cpu` minus the first sample's `cpu`.

## 5. Rules

Evaluate in the order given and return the first rule that matches. All
comparisons are strictly greater-than.

| # | Rule | Condition | Verdict |
|---|------|-----------|---------|
| 1 | Disk cascade | disk rate over `disk_io_rate_per_min` **and** gc rate over `gc_pause_ms_per_min` **and** last cpu over `cpu_hot_pct` | `DISK_IO_SATURATION` |
| 2 | Network saturation | net rate over `net_rate_per_min` | `NET_SATURATION` |
| 3 | CPU bottleneck | last cpu over `cpu_bottleneck_pct` **and** cpu jump over `cpu_jump_pct` | `CPU_BOTTLENECK` |
| 4 | Memory pressure | last mem over `mem_hot_pct` | `MEM_PRESSURE` |
| 5 | — | none of the above | `NO_FAULT` |

Rule 1 sits above rule 3 deliberately. When a host is thrashing its disk and
collecting garbage, the CPU burn is a *consequence*: routing that incident to
the CPU rotation is the single most common misdiagnosis this runbook exists to
prevent. Rule 2 sits between them for the same reason — a saturated uplink
starves the workload and the CPU reading follows.

## 6. Verdict payloads

* **`DISK_IO_SATURATION`** — reports `secondary` as `GC_PRESSURE` (rule 1
  already established the GC rate crossed), and `cpu_suspect` as `False`. The
  cascade *causes* the CPU burn, so CPU is affirmatively exonerated regardless
  of how high it reads.
* **`NET_SATURATION`** — reports `cpu_suspect`. Network saturation does not
  exonerate CPU: the two can be independent, so the field is not a constant.
  It is `True` when the last sample's cpu is over `cpu_hot_pct` and `False`
  otherwise.
* **`MEM_PRESSURE`** — reports `secondary` as `GC_PRESSURE` **only if** the gc
  rate also crossed `gc_pause_ms_per_min` (memory pressure and GC pressure
  usually travel together, but not always, and calling GC when GC is quiet
  sends the on-call reading the wrong heap dump). If the gc rate did not cross,
  the verdict carries no `secondary` key at all.
* **`CPU_BOTTLENECK`**, **`NO_FAULT`**, **`INSUFFICIENT_DATA`** — cause only,
  no additional keys.

## 7. Changelog

* **v2 (this document).** Supersedes `retired/runbook-v1.md`. Changes from v1:
  the disk cascade is evaluated *before* the CPU rule (v1's ordering routed
  incident 2023-11-04 to the CPU rotation for six hours while the array was the
  actual fault); counter thresholds became per-minute rates rather than raw
  window differences; the network rule was added; thresholds were extracted
  into the dated `threshold-policy.md` table rather than being quoted inline,
  so that historical windows can be re-judged correctly.
* **v1 (retired).** Kept under `retired/` for audit. Its rule ordering and its
  inline absolute thresholds are both wrong for anything analysed today.
