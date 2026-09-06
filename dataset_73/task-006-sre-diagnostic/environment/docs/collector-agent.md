---
title: Telemetry collector agent — consumer notes
owner: platform-observability
status: IN FORCE
---

# Telemetry collector agent — consumer notes

The host agent samples the platform metric series once per scrape interval and
forwards each sample to whatever downstream consumer is registered. This
document describes what a consumer receives and what it is obliged to do with
it before analysing anything.

## 1. Sample shape

A forwarded sample carries a timestamp plus five readings. Downstream ingest
APIs conventionally name their parameters after the short form, so the mapping
between the ingest parameter and the platform series it carries is worth
writing down explicitly:

| ingest parameter | platform metric series | unit |
|------------------|------------------------|------|
| `t`              | (sample timestamp)     | epoch seconds |
| `cpu`            | `cpu_util_pct`         | percent |
| `mem`            | `mem_util_pct`         | percent |
| `disk`           | `disk_io_ops_total`    | I/O operations |
| `net`            | `net_bytes_total`      | bytes |
| `gc`             | `gc_pause_ms_total`    | milliseconds |

The suffixes are meaningful. See `metric-naming.md` for what each one obliges a
consumer to do.

All five readings in a sample come from the same agent process, so a restart of
that process affects all of them at once.

## 2. Delivery is best-effort and unordered

The forwarder speaks UDP. There is no delivery guarantee and no ordering
guarantee, and in practice both are violated on a busy host:

* **Loss and retransmit.** A sample that the collector does not acknowledge
  within the retransmit window is re-sent. By the time the re-sent copy
  arrives, samples *newer* than it have usually already been delivered. So the
  order in which a consumer receives samples is arrival order, not time order.
* **Supersession.** A re-sent copy carries the **same timestamp** as the
  original and the corrected reading for that timestamp. The later-arriving
  copy is authoritative and replaces any earlier copy bearing that timestamp.
  This happens routinely: the first transmission is often assembled before the
  scrape has finished settling, and the retransmit carries the settled values.

A consumer must therefore reconstruct the window before analysing it:

1. Collapse samples that share a timestamp, keeping the **most recently
   received** copy of that timestamp.
2. Order what remains ascending by timestamp.

Only the reconstructed window has a meaningful "earliest" and "latest" sample.
Taking the first and last elements of the arrival-ordered buffer is a common
and expensive mistake — on any window that contains a retransmit it reads the
wrong endpoints, and endpoint readings are what the gauge thresholds compare.

## 3. Counter reset recovery

For a metric that is a cumulative counter (see `metric-naming.md` for which
suffix denotes one), the agent restarting mid-window makes the series step
backwards. The recovery rule, applied to **consecutive samples of the ordered
window**:

* If the later reading is greater than or equal to the earlier one, the step
  contributed `later - earlier`.
* If the later reading is **less** than the earlier one, the agent restarted
  during that step. Because the counter restarts at zero, everything the
  counter has accumulated since the restart is already in the later reading —
  so the step contributed **the later reading itself**.

The window total for that counter is the sum of the per-step contributions.

Note that the second branch is not "skip the step". Skipping discards all the
activity that occurred after the restart, which on a window whose restart lands
early can be most of the window.

## 4. Timestamps

Timestamps are epoch seconds, taken from the host clock at scrape time. They
are used both to order the window and to establish *when* the incident
happened, which matters for anything that is versioned by date.
