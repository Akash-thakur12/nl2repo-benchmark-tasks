"""Incident root-cause classifier.

Implements environment/docs/runbook-incident-classification.md (v2), reading
its thresholds from environment/docs/threshold-policy.md and its window
reconstruction / counter-reset semantics from
environment/docs/collector-agent.md + environment/docs/metric-naming.md.
"""
from __future__ import annotations

#: Dated threshold policy, transcribed from docs/threshold-policy.md.
#: Ordered ascending by ``effective_from``.
POLICY_REVISIONS = [
    {
        "rev": "r1",
        "effective_from": 0,
        "disk_io_rate_per_min": 100.0,
        "gc_pause_ms_per_min": 200.0,
        "net_rate_per_min": 500.0,
        "cpu_hot_pct": 80.0,
        "cpu_bottleneck_pct": 90.0,
        "cpu_jump_pct": 30.0,
        "mem_hot_pct": 90.0,
    },
    {
        "rev": "r2",
        "effective_from": 1704067200,
        "disk_io_rate_per_min": 150.0,
        "gc_pause_ms_per_min": 250.0,
        "net_rate_per_min": 400.0,
        "cpu_hot_pct": 85.0,
        "cpu_bottleneck_pct": 90.0,
        "cpu_jump_pct": 25.0,
        "mem_hot_pct": 92.0,
    },
    {
        "rev": "r3",
        "effective_from": 1735689600,
        "disk_io_rate_per_min": 60.0,
        "gc_pause_ms_per_min": 120.0,
        "net_rate_per_min": 300.0,
        "cpu_hot_pct": 75.0,
        "cpu_bottleneck_pct": 88.0,
        "cpu_jump_pct": 20.0,
        "mem_hot_pct": 88.0,
    },
]

#: Ingest parameters carrying ``_total`` counter series (metric-naming.md).
COUNTER_FIELDS = ("disk", "net", "gc")

#: Runbook §2 admissibility: shorter windows are scrape jitter, not signal.
MIN_SPAN_SECONDS = 30.0


def _policy_for(window_start_t):
    """Revision in force when the window opened (runbook §3).

    The greatest ``effective_from`` not later than the first sample's
    timestamp -- deliberately not the newest revision, and deliberately not
    the revision in force at the window's end.
    """
    chosen = POLICY_REVISIONS[0]
    for rev in POLICY_REVISIONS:
        if rev["effective_from"] <= window_start_t:
            chosen = rev
        else:
            break
    return chosen


def _counter_total(window, field):
    """Window total for a cumulative ``_total`` series (collector-agent.md §3).

    A decrease between consecutive ordered samples means the agent restarted;
    because the counter restarts at zero, the post-restart reading *is* the
    activity accumulated since the restart, so that step contributes the new
    reading itself rather than being skipped.
    """
    total = 0.0
    for earlier, later in zip(window, window[1:]):
        lo, hi = earlier[field], later[field]
        total += (hi - lo) if hi >= lo else hi
    return total


class SreDiagEngine:
    """Classify an incident root cause from a window of telemetry samples."""

    def __init__(self, config=None):
        self._samples = []

    def reset(self):
        self._samples = []

    def configure(self, options):
        self._samples = []

    def add(self, t, cpu, mem, disk, net, gc):
        # Arrival order, not time order: the forwarder is best-effort UDP and a
        # retransmit lands after samples newer than itself.
        self._samples.append(
            {"t": t, "cpu": cpu, "mem": mem, "disk": disk, "net": net, "gc": gc}
        )

    def _window(self):
        """Reconstruct the analysable window (collector-agent.md §2).

        Collapse duplicate timestamps keeping the most recently received copy,
        then order ascending by timestamp.
        """
        by_t = {}
        for sample in self._samples:
            by_t[sample["t"]] = sample          # last write wins: supersession
        return [by_t[k] for k in sorted(by_t)]

    def diagnose(self):
        window = self._window()

        # Runbook §2 -- admissibility, evaluated on the reconstructed window.
        if len(window) < 2:
            return {"cause": "INSUFFICIENT_DATA"}
        span = float(window[-1]["t"] - window[0]["t"])
        if span < MIN_SPAN_SECONDS:
            return {"cause": "INSUFFICIENT_DATA"}

        policy = _policy_for(window[0]["t"])

        # Runbook §4 -- counters become per-minute rates over the window span;
        # gauges are read absolutely from the last in-window sample.
        rates = {
            field: _counter_total(window, field) * 60.0 / span
            for field in COUNTER_FIELDS
        }
        cpu_last = window[-1]["cpu"]
        mem_last = window[-1]["mem"]
        cpu_jump = cpu_last - window[0]["cpu"]

        gc_hot = rates["gc"] > policy["gc_pause_ms_per_min"]
        cpu_hot = cpu_last > policy["cpu_hot_pct"]

        # Runbook §5 -- first match wins.
        if rates["disk"] > policy["disk_io_rate_per_min"] and gc_hot and cpu_hot:
            return {"cause": "DISK_IO_SATURATION",
                    "secondary": "GC_PRESSURE",
                    "cpu_suspect": False}

        if rates["net"] > policy["net_rate_per_min"]:
            return {"cause": "NET_SATURATION", "cpu_suspect": bool(cpu_hot)}

        if cpu_last > policy["cpu_bottleneck_pct"] and cpu_jump > policy["cpu_jump_pct"]:
            return {"cause": "CPU_BOTTLENECK"}

        if mem_last > policy["mem_hot_pct"]:
            verdict = {"cause": "MEM_PRESSURE"}
            if gc_hot:
                verdict["secondary"] = "GC_PRESSURE"
            return verdict

        return {"cause": "NO_FAULT"}
