---
title: Alert threshold policy
owner: platform-sre
status: IN FORCE
applies_to: incident root-cause classification
---

# Alert threshold policy

This is the single source of truth for every numeric threshold used by the
incident root-cause classifier. No threshold value is duplicated anywhere else
in this repository; if you find one hardcoded in a script, that script is stale.

## Revisions

Thresholds are revised as the fleet changes. Each revision carries an
`effective_from` value in epoch seconds (UTC). A revision remains in force from
its `effective_from` until the `effective_from` of the next revision.

| rev | effective_from | disk_io_rate_per_min | gc_pause_ms_per_min | net_rate_per_min | cpu_hot_pct | cpu_bottleneck_pct | cpu_jump_pct | mem_hot_pct |
|-----|----------------|----------------------|---------------------|------------------|-------------|--------------------|--------------|-------------|
| r1  | 0              | 100                  | 200                 | 500              | 80          | 90                 | 30           | 90          |
| r2  | 1704067200     | 150                  | 250                 | 400              | 85          | 90                 | 25           | 92          |
| r3  | 1735689600     | 60                   | 120                 | 300              | 75          | 88                 | 20           | 88          |

Notes on the revisions, for context only:

* **r1** is the original 2022 table, carried over unchanged from the v1 runbook.
* **r2** (2024-01-01) raised the disk and GC lines after the NVMe rollout made
  the old disk line fire constantly on healthy hosts, and lowered the network
  line after the uplink upgrade.
* **r3** (2025-01-01) tightened everything following the density migration:
  hosts now run roughly twice the workload per box, so the same absolute rate
  is a much stronger signal than it used to be.

## Column semantics

* Columns ending `_rate_per_min` are thresholds on **per-minute rates** derived
  from cumulative counters. They are not thresholds on a raw endpoint-to-endpoint
  difference, and they are not thresholds on an instantaneous reading.
* Columns ending `_pct` are thresholds on **gauge** readings, expressed as a
  percentage.
* Every comparison against every column in this table is strictly greater-than.
  A reading that lands exactly on the line has not crossed it.

See `runbook-incident-classification.md` for which revision applies to a given
window and for the rules these thresholds feed.
