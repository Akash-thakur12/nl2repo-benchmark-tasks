import pytest
from engine.engine import SreDiagEngine


def test_disk_gc_cascade_beats_cpu():
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 92, 70, 200, 8, 400)
    r = e.diagnose()
    assert r["cause"] == "DISK_IO_SATURATION"
    assert r["secondary"] == "GC_PRESSURE"
    assert r["cpu_suspect"] is False


def test_cpu_bottleneck():
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 95, 70, 15, 8, 10)
    assert e.diagnose()["cause"] == "CPU_BOTTLENECK"


def test_mem_pressure():
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 40, 95, 12, 8, 10)
    assert e.diagnose()["cause"] == "MEM_PRESSURE"


def test_no_fault():
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 30, 55, 12, 8, 12)
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_high_cpu_without_jump_is_not_bottleneck():
    e = SreDiagEngine()
    e.add(0, 88, 50, 10, 5, 5)     # already high, only +7 rise
    e.add(60, 95, 55, 12, 8, 10)
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_disk_delta_without_gc_is_not_cascade():
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 95, 55, 400, 8, 20)   # disk spiked, gc flat -> falls through to CPU rule
    assert e.diagnose()["cause"] == "CPU_BOTTLENECK"


def test_insufficient_data():
    e = SreDiagEngine()
    assert e.diagnose()["cause"] == "INSUFFICIENT_DATA"
    e.add(0, 50, 50, 10, 5, 5)
    assert e.diagnose()["cause"] == "INSUFFICIENT_DATA"


def test_reset_and_configure_clear_samples():
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 92, 70, 200, 8, 400)
    assert e.diagnose()["cause"] == "DISK_IO_SATURATION"
    e.reset()
    assert e.diagnose()["cause"] == "INSUFFICIENT_DATA"
    e.add(0, 1, 1, 1, 1, 1)
    e.add(1, 2, 2, 2, 2, 2)
    e.configure({})
    assert e.diagnose()["cause"] == "INSUFFICIENT_DATA"


def test_thresholds_are_strict_not_inclusive():
    """Every threshold in section 3 is "greater than", so a reading that sits
    exactly on the line has not crossed it. A window whose disk, GC and CPU all
    land precisely on their thresholds is not a disk cascade."""
    e = SreDiagEngine()
    e.add(0, 80.0, 50, 10.0, 5, 5.0)
    e.add(60, 80.0, 50, 110.0, 8, 205.0)   # disk +100.0, gc +200.0, cpu 80.0
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_disk_cascade_needs_every_reading_past_its_threshold():
    """Two of the three exactly on the line and one past it is still not a
    cascade - the rule is a conjunction of three strict comparisons."""
    e = SreDiagEngine()
    e.add(0, 20.0, 50, 10.0, 5, 5.0)
    e.add(60, 80.0, 50, 200.0, 8, 400.0)   # disk and gc past, cpu exactly 80.0
    assert e.diagnose()["cause"] != "DISK_IO_SATURATION"


def test_cpu_rule_boundary_on_both_halves():
    """The CPU rule needs the last sample past CPU_BOTTLENECK and the rise past
    CPU_JUMP. Sitting exactly on either line is not enough."""
    e = SreDiagEngine()
    e.add(0, 50.0, 50, 10, 5, 5)
    e.add(60, 90.0, 50, 10, 8, 5)          # cpu exactly 90.0, jump 40.0
    assert e.diagnose()["cause"] != "CPU_BOTTLENECK"

    e2 = SreDiagEngine()
    e2.add(0, 65.0, 50, 10, 5, 5)
    e2.add(60, 95.0, 50, 10, 8, 5)         # cpu 95.0 but jump exactly 30.0
    assert e2.diagnose()["cause"] != "CPU_BOTTLENECK"


def test_memory_threshold_is_strict():
    """Memory exactly at MEM_HOT has not crossed it."""
    e = SreDiagEngine()
    e.add(0, 20, 50.0, 10, 5, 5)
    e.add(60, 30, 90.0, 10, 8, 5)
    assert e.diagnose()["cause"] == "NO_FAULT"

    e2 = SreDiagEngine()
    e2.add(0, 20, 50.0, 10, 5, 5)
    e2.add(60, 30, 90.1, 10, 8, 5)
    assert e2.diagnose()["cause"] == "MEM_PRESSURE"


def test_disk_delta_exactly_on_its_threshold_does_not_fire():
    """Disk exactly at DISK_DELTA, with GC and CPU both well past theirs. The
    cascade still must not fire: the disk comparison is strict too."""
    e = SreDiagEngine()
    e.add(0, 88.0, 50, 10.0, 5, 5.0)
    e.add(60, 92.0, 50, 110.0, 8, 500.0)   # disk +100.0 exactly, gc +495, cpu 92
    assert e.diagnose()["cause"] != "DISK_IO_SATURATION"


# ---------------------------------------------------------------------------
# Crux E/H -- the window must be reconstructed from arrival order before the
# endpoints, the distinct-timestamp count or the span mean anything.
# (environment/docs/collector-agent.md section 2, runbook sections 1-2)
# ---------------------------------------------------------------------------

def test_window_is_ordered_by_timestamp_not_arrival():
    """The forwarder is best-effort UDP, so a retransmitted sample arrives
    after samples newer than itself. The last sample of the window is the one
    with the greatest timestamp, not the one that arrived last."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(120, 95, 50, 12, 8, 8)      # newest sample, arrives second
    e.add(60, 40, 50, 11, 7, 7)       # late retransmit of an older scrape
    assert e.diagnose()["cause"] == "CPU_BOTTLENECK"


def test_window_first_sample_is_earliest_not_first_arrival():
    """The CPU jump is measured from the earliest timestamp in the window. If
    the first sample to arrive is not the earliest one, using it understates
    the rise and the bottleneck disappears."""
    e = SreDiagEngine()
    e.add(60, 88, 50, 11, 7, 7)       # arrives first, but is the middle sample
    e.add(0, 20, 50, 10, 5, 5)
    e.add(120, 95, 50, 12, 8, 8)
    assert e.diagnose()["cause"] == "CPU_BOTTLENECK"


def test_duplicate_timestamp_is_superseded_by_the_later_arrival():
    """A retransmit carries the same timestamp and the corrected reading. The
    most recently received copy of a timestamp wins; the earlier copy is
    discarded, not kept and not averaged."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 95, 50, 12, 8, 8)       # first transmission, unsettled reading
    e.add(60, 30, 50, 12, 8, 8)       # retransmit of the same scrape, settled
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_repeated_single_timestamp_is_insufficient_data():
    """Admissibility counts DISTINCT timestamps in the reconstructed window,
    not raw samples ingested. Three copies of one scrape give no interval."""
    e = SreDiagEngine()
    e.add(60, 20, 50, 10, 5, 5)
    e.add(60, 92, 70, 400, 8, 900)
    e.add(60, 95, 95, 900, 9, 2000)
    assert e.diagnose()["cause"] == "INSUFFICIENT_DATA"


def test_window_shorter_than_minimum_span_is_insufficient_data():
    """A window spanning under 30 seconds extrapolates a per-minute rate by
    more than 2x from a single scrape interval, so it is not classified."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(20, 95, 50, 400, 8, 900)
    assert e.diagnose()["cause"] == "INSUFFICIENT_DATA"


def test_span_of_exactly_thirty_seconds_is_admissible():
    """The span guard is 'shorter than 30 seconds'. Exactly 30 seconds is
    admissible and must be classified normally."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(30, 95, 50, 12, 6, 6)
    assert e.diagnose()["cause"] == "CPU_BOTTLENECK"


def test_ordering_is_applied_before_counter_reset_detection():
    """Reset detection walks consecutive pairs of the ordered window, so a
    window analysed in arrival order both mis-detects a restart and divides by
    the wrong span."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 1000, 5, 5)
    e.add(300, 92, 50, 1400, 9, 60)
    e.add(60, 40, 50, 1100, 6, 20)
    assert e.diagnose()["cause"] == "CPU_BOTTLENECK"


# ---------------------------------------------------------------------------
# Crux B/D -- disk/net/gc are `_total` cumulative counters, and their
# thresholds are per-minute rates over the window span.
# (collector-agent.md sections 1 and 3, metric-naming.md, runbook section 4)
# ---------------------------------------------------------------------------

def test_counter_reset_preserves_the_disk_cascade():
    """The agent restarted mid-window, so the disk and GC counters restarted at
    zero. A raw last-minus-first goes negative and hands the incident to CPU --
    the exact misdiagnosis the cascade rule exists to prevent."""
    e = SreDiagEngine()
    e.add(0, 22, 60, 1000, 5000, 5000)
    e.add(60, 70, 62, 1250, 5150, 5400)
    e.add(120, 92, 63, 90, 60, 200)     # agent restart: every counter reset
    r = e.diagnose()
    assert r["cause"] == "DISK_IO_SATURATION"
    assert r["secondary"] == "GC_PRESSURE"
    assert r["cpu_suspect"] is False


def test_counter_reset_step_contributes_the_post_restart_reading():
    """On a restart step the post-restart reading IS the activity accumulated
    since the restart, so the step contributes that reading. Merely dropping
    the decreasing step under-counts and loses the verdict."""
    e = SreDiagEngine()
    e.add(0, 30, 50, 10, 9000, 10)
    e.add(60, 35, 52, 12, 9600, 12)
    e.add(120, 85, 55, 14, 900, 14)     # net counter restarted at zero
    r = e.diagnose()
    assert r["cause"] == "NET_SATURATION"
    assert r["cpu_suspect"] is True


def test_counter_rates_are_per_minute_over_the_window_span():
    """A 30-second window carrying half a minute of activity is at the same
    per-minute rate as a 60-second window carrying a full minute of it. Raw
    window differences under-fire here."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 100, 10, 100)
    e.add(30, 92, 50, 160, 12, 230)     # disk 120/min, gc 260/min
    assert e.diagnose()["cause"] == "DISK_IO_SATURATION"


def test_long_window_is_not_inflated_by_raw_differences():
    """Over five minutes a raw difference looks five times worse than the same
    underlying rate does over one minute. Normalised, this window is quiet on
    disk and GC and the CPU rule owns it."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 100, 10, 100)
    e.add(300, 92, 50, 500, 60, 800)    # disk 80/min, gc 140/min: both under
    assert e.diagnose()["cause"] == "CPU_BOTTLENECK"


def test_mem_pressure_gains_gc_secondary_only_when_the_gc_rate_crossed():
    """Memory pressure reports a GC secondary only if the GC *rate* also
    crossed. Across a counter restart that rate is only visible once the reset
    is reconstructed."""
    e = SreDiagEngine()
    e.add(0, 30, 60, 10, 20, 5000)
    e.add(60, 32, 80, 12, 22, 5400)
    e.add(120, 35, 95, 14, 24, 260)     # gc counter restarted at zero
    r = e.diagnose()
    assert r["cause"] == "MEM_PRESSURE"
    assert r["secondary"] == "GC_PRESSURE"


def test_mem_pressure_omits_secondary_when_gc_is_quiet():
    """When GC is quiet the verdict carries no `secondary` key at all -- not
    the key with a null or false value."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 30, 95, 12, 8, 10)
    r = e.diagnose()
    assert r["cause"] == "MEM_PRESSURE"
    assert "secondary" not in r


# ---------------------------------------------------------------------------
# Crux I -- the threshold revision in force at the window start governs.
# (threshold-policy.md effective_from column, runbook section 3)
# ---------------------------------------------------------------------------

def test_r2_era_window_uses_r2_disk_and_gc_lines():
    """A 2024 window is judged against the revision effective 2024-01-01. Under
    the newest revision this same window is a disk cascade; it is not."""
    e = SreDiagEngine()
    e.add(1725235200, 30, 55, 3000, 9000, 2000)
    e.add(1725235260, 86, 60, 3120, 9100, 2260)   # disk 120/min, gc 260/min
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_r1_era_cpu_line_is_not_the_newest_cpu_line():
    """A 2022-era window sits under the original revision, whose CPU
    bottleneck line is 90 and whose jump line is 30. The newest revision
    lines (88 and 20) would fire on this window."""
    e = SreDiagEngine()
    e.add(0, 64, 50, 10, 5, 5)
    e.add(60, 89, 50, 12, 8, 8)                   # cpu 89, jump 25
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_r1_era_memory_line_is_not_the_newest_memory_line():
    """Same for memory: 89% is under the original 90 line and over the newest
    88 line."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 5, 5)
    e.add(60, 30, 89, 12, 8, 8)
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_r2_era_memory_line_is_neither_r1_nor_r3():
    """A 2024 window at 91% memory is quiet: the 2024 revision raised the
    memory line to 92. Both the original (90) and the newest (88) revisions
    would report memory pressure here."""
    e = SreDiagEngine()
    e.add(1710720000, 20, 50, 10, 5, 5)
    e.add(1710720060, 30, 91, 12, 8, 8)
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_straddling_window_is_judged_by_the_revision_it_opened_under():
    """This window opens 100 seconds before a revision boundary and closes 100
    seconds after it. It is judged entirely under the revision in force when it
    opened -- not the one in force when it closed."""
    e = SreDiagEngine()
    e.add(1704067100, 20, 50, 1000, 10, 1000)
    e.add(1704067300, 82, 50, 1400, 30, 1800)     # disk 120/min, gc 240/min
    r = e.diagnose()
    assert r["cause"] == "DISK_IO_SATURATION"
    assert r["cpu_suspect"] is False


# ---------------------------------------------------------------------------
# The network rule and the computed cpu_suspect field (runbook sections 5-6).
# ---------------------------------------------------------------------------

def test_net_saturation_fires_on_the_net_rate():
    """A saturated uplink is its own verdict, driven by the net counter rate."""
    e = SreDiagEngine()
    e.add(0, 40, 50, 10, 1000, 5)
    e.add(60, 50, 55, 12, 1600, 8)                # net 600/min
    assert e.diagnose()["cause"] == "NET_SATURATION"


def test_net_saturation_cpu_suspect_is_computed_not_constant():
    """Unlike the disk cascade, network saturation does not exonerate CPU:
    cpu_suspect is True exactly when the last CPU reading is over the hot
    line, and False otherwise."""
    hot = SreDiagEngine()
    hot.add(0, 40, 50, 10, 1000, 5)
    hot.add(60, 85, 55, 12, 1600, 8)
    r_hot = hot.diagnose()
    assert r_hot["cause"] == "NET_SATURATION"
    assert r_hot["cpu_suspect"] is True

    cool = SreDiagEngine()
    cool.add(0, 40, 50, 10, 1000, 5)
    cool.add(60, 50, 55, 12, 1600, 8)
    r_cool = cool.diagnose()
    assert r_cool["cause"] == "NET_SATURATION"
    assert r_cool["cpu_suspect"] is False


def test_disk_cascade_outranks_net_saturation():
    """Rule order: when both the disk cascade and the network rule match, the
    cascade wins and CPU is affirmatively exonerated."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 1000, 5)
    e.add(60, 92, 55, 200, 1600, 400)
    r = e.diagnose()
    assert r["cause"] == "DISK_IO_SATURATION"
    assert r["cpu_suspect"] is False


def test_net_saturation_outranks_cpu_bottleneck():
    """A saturated uplink starves the workload, so it is diagnosed ahead of the
    CPU rule even when the CPU rule would also match."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 10, 1000, 5)
    e.add(60, 95, 55, 12, 1600, 8)
    assert e.diagnose()["cause"] == "NET_SATURATION"


# ---------------------------------------------------------------------------
# Capstone and shipped captures.
# ---------------------------------------------------------------------------

def test_capstone_ordering_reset_and_policy_era_together():
    """A 2024 window delivered out of order, containing a superseding
    retransmit and an agent restart, whose verdict is only correct when the
    2024 revision is applied to the reconstructed, reset-recovered window."""
    e = SreDiagEngine()
    e.add(1710720060, 70, 62, 1250, 5150, 5400)   # middle scrape, arrives first
    e.add(1710720120, 45, 63, 90, 60, 150)        # unsettled first transmission
    e.add(1710720000, 22, 60, 1000, 5000, 5000)
    e.add(1710720120, 92, 63, 90, 60, 200)        # retransmit supersedes it
    r = e.diagnose()
    assert r["cause"] == "DISK_IO_SATURATION"
    assert r["secondary"] == "GC_PRESSURE"
    assert r["cpu_suspect"] is False


def test_shipped_incident_captures_replay_to_their_recorded_verdicts():
    """Every reviewed capture in environment/samples/incidents replays through
    the engine to the verdict the on-call engineer recorded at the time."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    candidates = [
        root / "environment" / "samples" / "incidents",   # task tree
        root / "samples" / "incidents",                   # deployed image
        Path("/app/samples/incidents"),
    ]
    for d in candidates:
        if d.is_dir():
            break
    else:                                                 # pragma: no cover
        raise AssertionError("shipped incident captures are missing")
    incidents = sorted(d.glob("*.json"))
    assert len(incidents) >= 6, "shipped incident captures are missing"

    for path in incidents:
        doc = json.loads(path.read_text())
        e = SreDiagEngine()
        for s in doc["samples_in_arrival_order"]:
            e.add(s["t"], s["cpu_util_pct"], s["mem_util_pct"],
                  s["disk_io_ops_total"], s["net_bytes_total"],
                  s["gc_pause_ms_total"])
        assert e.diagnose() == doc["recorded_verdict"], path.name


def test_diagnose_is_repeatable_and_non_mutating():
    """diagnose() is a pure function of the samples ingested so far: calling it
    twice with no intervening add() returns an equal verdict, and the ingested
    samples are not consumed or reordered in place."""
    e = SreDiagEngine()
    e.add(120, 92, 63, 90, 60, 200)
    e.add(0, 22, 60, 1000, 5000, 5000)
    e.add(60, 70, 62, 1250, 5150, 5400)
    first = e.diagnose()
    second = e.diagnose()
    assert first == second
    assert first["cause"] == "DISK_IO_SATURATION"


# ---------------------------------------------------------------------------
# Boundary conditions on the new machinery.
# ---------------------------------------------------------------------------

def test_window_opening_exactly_on_a_revision_boundary_uses_the_new_revision():
    """A revision is in force *from* its effective_from, inclusive. A window
    whose first sample lands exactly on the boundary second is judged under the
    revision that starts there, not the one it replaced."""
    e = SreDiagEngine()
    e.add(1704067200, 30, 55, 3000, 9000, 2000)
    e.add(1704067260, 86, 60, 3120, 9100, 2260)   # disk 120/min, gc 260/min
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_flat_counter_step_is_not_treated_as_a_restart():
    """A counter that reads the same at two consecutive scrapes did not move;
    it did not restart. Only a strict *decrease* means a restart. Treating an
    equal reading as a restart credits the whole cumulative value as activity
    and invents a disk cascade out of an idle disk."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 1000, 100, 1000)
    e.add(60, 50, 50, 1000, 100, 1300)            # disk flat across this step
    e.add(120, 85, 50, 1150, 100, 1600)
    assert e.diagnose()["cause"] == "NO_FAULT"


def test_gc_rate_exactly_on_its_threshold_does_not_complete_the_cascade():
    """The GC comparison is strict and is made against the *rate*. Disk and CPU
    are both past their lines here; GC lands exactly on its own, so the cascade
    does not fire and the window falls through to the CPU rule."""
    e = SreDiagEngine()
    e.add(0, 20, 50, 100, 10, 100)
    e.add(60, 92, 50, 250, 12, 300)               # disk 150/min, gc 200.0/min
    assert e.diagnose()["cause"] == "CPU_BOTTLENECK"


def test_net_rate_exactly_on_its_threshold_does_not_fire():
    """The network comparison is strict too: a rate sitting exactly on the
    policy line has not crossed it."""
    e = SreDiagEngine()
    e.add(0, 40, 50, 10, 1000, 5)
    e.add(60, 50, 55, 12, 1500, 8)                # net 500.0/min exactly
    assert e.diagnose()["cause"] == "NO_FAULT"
