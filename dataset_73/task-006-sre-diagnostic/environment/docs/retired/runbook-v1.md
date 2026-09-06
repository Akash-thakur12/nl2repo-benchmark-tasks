---
title: Incident root-cause classification (v1)
owner: platform-sre
status: RETIRED
retired_on: 2023-12-01
superseded_by: ../runbook-incident-classification.md
warning: Do not implement. Kept for audit of pre-2024 incident reviews only.
---

# Incident root-cause classification — v1 (RETIRED)

> **This document is retired.** It is reproduced verbatim as it stood on
> 2023-12-01 so that pre-2024 incident reviews can be audited against the
> playbook that was actually in force at the time. It does not describe current
> behaviour. See `../runbook-incident-classification.md`.

## Window

Take the first sample delivered and the last sample delivered. Subtract.

## Rules

Evaluate in order:

1. If fewer than two samples: `INSUFFICIENT_DATA`.
2. If the last sample's CPU is above 90% and CPU rose by more than 30 points:
   `CPU_BOTTLENECK`.
3. If disk I/O rose by more than 100 and GC pause time rose by more than 200 ms
   and the last sample's CPU is above 80%: `DISK_IO_SATURATION`, with
   `secondary: GC_PRESSURE` and `cpu_suspect: false`.
4. If the last sample's memory is above 90%: `MEM_PRESSURE`.
5. Otherwise: `NO_FAULT`.

All figures above are absolute increases across the window, not rates. There is
no minimum window length and no network rule.

## Known problems with this version

Recorded here at retirement, and all fixed in v2:

* Rule 2 before rule 3 means a disk-and-GC cascade whose CPU also crosses 90 is
  reported as a CPU bottleneck. This misrouted 2023-11-04.
* Absolute increases make a five-minute window look five times worse than a
  one-minute window with the same underlying rate.
* Thresholds are quoted inline, so re-analysing an old incident after a
  threshold change silently produces a verdict nobody ever saw.
