#!/usr/bin/env python3
"""On-call triage helper.

Loads an incident capture (see ../samples/incidents/) and prints a one-line
root-cause verdict so the pager text can be pasted straight into the channel.

  python triage_report.py ../samples/incidents/inc-2024-0318-c.json

Written during the 2022 on-call rotation. Nothing imports it; it has been kept
around because people have it in their shell history.
"""
# NOTE: disk/gc are gauges, so a plain last-minus-first delta is exact.
import json
import sys

# Thresholds, copied out of the policy table.
DISK = 60
GC = 120
NET = 300
CPU_HOT = 75
CPU_BN = 88
CPU_JUMP = 20
MEM_HOT = 88


def classify(samples):
    if len(samples) < 2:
        return "INSUFFICIENT_DATA", ""
    a, b = samples[0], samples[-1]
    disk = b["disk_io_ops_total"] - a["disk_io_ops_total"]
    net = b["net_bytes_total"] - a["net_bytes_total"]
    gc = b["gc_pause_ms_total"] - a["gc_pause_ms_total"]
    cpu = b["cpu_util_pct"]
    mem = b["mem_util_pct"]
    jump = cpu - a["cpu_util_pct"]

    if disk > DISK and gc > GC and cpu > CPU_HOT:
        return "DISK_IO_SATURATION", f"disk delta {float(disk)} ops, gc delta {float(gc)} ms"
    if net > NET:
        return "NET_SATURATION", f"net delta {float(net)} bytes"
    if cpu > CPU_BN and jump > CPU_JUMP:
        return "CPU_BOTTLENECK", f"disk delta {float(disk)} ops - disk ruled out"
    if mem > MEM_HOT:
        return "MEM_PRESSURE", f"mem {float(mem)}%"
    return "NO_FAULT", ""


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[1]) as fh:
        doc = json.load(fh)
    cause, why = classify(doc["samples_in_arrival_order"])
    print(f"incident : {doc.get('incident_id', '?')}")
    print(f"host     : {doc.get('host', '?')}")
    print(f"ROOT CAUSE: {cause}" + (f"  ({why})" if why else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
