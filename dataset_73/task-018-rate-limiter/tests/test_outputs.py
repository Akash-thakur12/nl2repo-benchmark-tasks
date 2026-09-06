import pytest
from engine.engine import RateLimiterEngine


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_burst_then_deny():
    e = RateLimiterEngine({"capacity": 3, "rate": 0.0, "clock": Clock()})
    assert [e.allow("k") for _ in range(4)] == [True, True, True, False]


def test_refill_over_time():
    clk = Clock()
    e = RateLimiterEngine({"capacity": 2, "rate": 100.0, "clock": clk})
    assert e.allow("k") and e.allow("k")
    assert e.allow("k") is False
    clk.advance(0.05)                     # 100 tok/s * 0.05s = 5 tokens (capped at 2)
    assert e.allow("k") is True


def test_per_key_isolation():
    e = RateLimiterEngine({"capacity": 1, "rate": 0.0, "clock": Clock()})
    assert e.allow("a") and not e.allow("a")
    assert e.allow("b")


def test_cost_greater_than_one():
    e = RateLimiterEngine({"capacity": 5, "rate": 0.0, "clock": Clock()})
    assert e.allow("k", cost=3) is True
    assert e.allow("k", cost=3) is False   # only 2 left
    assert e.allow("k", cost=2) is True


def test_tokens_readout():
    clk = Clock()
    e = RateLimiterEngine({"capacity": 10, "rate": 1.0, "clock": clk})
    assert e.tokens("k") == 10
    e.allow("k", cost=4)
    assert e.tokens("k") == 6
    clk.advance(3)
    assert e.tokens("k") == 9


def test_rate_zero_never_refills():
    clk = Clock()
    e = RateLimiterEngine({"capacity": 2, "rate": 0.0, "clock": clk})
    e.allow("k"); e.allow("k")
    clk.advance(1_000_000)
    assert e.allow("k") is False


def test_sliding_window_allows_up_to_max_then_denies():
    e = RateLimiterEngine({"clock": Clock()})
    assert [e.sliding_window("k", 10, 3) for _ in range(5)] == [True, True, True, False, False]


def test_sliding_window_frees_as_time_passes():
    clk = Clock()
    e = RateLimiterEngine({"clock": clk})
    for _ in range(3):
        assert e.sliding_window("k", 10, 3) is True
    assert e.sliding_window("k", 10, 3) is False
    clk.advance(11)                       # all three timestamps now outside the window
    assert e.sliding_window("k", 10, 3) is True


def test_sliding_window_is_per_key():
    e = RateLimiterEngine({"clock": Clock()})
    assert e.sliding_window("a", 5, 1) is True
    assert e.sliding_window("a", 5, 1) is False
    assert e.sliding_window("b", 5, 1) is True


def test_sliding_window_partial_expiry():
    clk = Clock()
    e = RateLimiterEngine({"clock": clk})
    assert e.sliding_window("k", 10, 2) is True     # t=1000
    clk.advance(6)
    assert e.sliding_window("k", 10, 2) is True     # t=1006, 2 in window
    assert e.sliding_window("k", 10, 2) is False
    clk.advance(5)                                  # t=1011, first (1000) expired
    assert e.sliding_window("k", 10, 2) is True


def test_reset_and_configure():
    e = RateLimiterEngine({"capacity": 1, "rate": 0.0, "clock": Clock()})
    e.allow("k")
    assert e.allow("k") is False
    e.reset()
    assert e.allow("k") is True
    e.configure({"capacity": 5})
    assert sum(e.allow("k") for _ in range(10)) == 5


@pytest.mark.parametrize("i", range(5))
def test_matrix(i):
    e = RateLimiterEngine({"capacity": 5, "rate": 0.0, "clock": Clock()})
    assert sum(e.allow("x") for _ in range(10)) == 5


# ---------------------------------------------------------------------------
# Gateway 4.3 behaviour.
#
# The rows below are environment/reference/policies.json verbatim, in file
# order (which is revision order, not effective_at order).  The expected values
# in these tests are the ones recorded in environment/capture/*.jsonl.
# ---------------------------------------------------------------------------

POLICIES = [
    {"tenant": "*", "capacity": 10, "rate": 1.0,
     "effective_at": 1704067200, "revision": 1,
     "note": "platform default at launch"},
    {"tenant": "acme", "capacity": 20, "rate": 2.0,
     "effective_at": 1704067200, "revision": 2,
     "note": "acme onboarding, negotiated burst"},
    {"tenant": "globex", "capacity": 8, "rate": 0.5,
     "effective_at": 1704067200, "revision": 3,
     "note": "globex onboarding"},
    {"tenant": "acme", "capacity": 12, "rate": 0.05,
     "effective_at": 1735690800, "revision": 4,
     "note": "acme post-incident settings"},
    {"tenant": "*", "capacity": 4, "rate": 0.25,
     "effective_at": 1735689900, "revision": 5,
     "note": "platform default tightened"},
    {"tenant": "globex", "capacity": 9, "rate": 0.5,
     "effective_at": 1735690200, "revision": 6,
     "note": "globex burst bump"},
    {"tenant": "globex", "capacity": 6, "rate": 0.2,
     "effective_at": 1735691400, "revision": 7,
     "note": "globex Q1 plan"},
    {"tenant": "initech", "capacity": 5, "rate": 0.1,
     "effective_at": 1735690200, "revision": 8,
     "note": "initech onboarding"},
    {"tenant": "globex", "capacity": 3, "rate": 0.2,
     "effective_at": 1735691400, "revision": 9,
     "note": "globex Q1 plan, amended: capacity was mis-keyed in r7"},
    {"tenant": "acme", "capacity": 5, "rate": 0.02,
     "effective_at": 1735690000, "revision": 10,
     "note": "backfill: settings acme actually ran under from 1735690000"},
    {"tenant": "acme", "capacity": 100, "rate": 5.0,
     "effective_at": 1735696800, "revision": 11,
     "note": "scheduled: acme enterprise upgrade"},
]


def limiter(t, **extra):
    """A policy-driven engine whose clock reads ``t``."""
    clk = Clock(t)
    cfg = {"policies": POLICIES, "clock": clk}
    cfg.update(extra)
    return RateLimiterEngine(cfg), clk


def burst(engine, key, ceiling=400):
    """How many cost-1 calls a fresh key is admitted before its first deny."""
    admitted = 0
    while admitted < ceiling and engine.allow(key):
        admitted += 1
    return admitted


# ------------------------------------------------------- policy resolution


def test_policy_row_in_force_at_first_touch():
    """capacity comes from the row governing the instant of first touch."""
    e, _ = limiter(1735690300.0)
    assert burst(e, "acme:10.0.0.7") == 5


def test_later_effective_at_supersedes_a_backfilled_row():
    """a row with a later effective_at governs even though its revision is lower."""
    e, _ = limiter(1735690900.0)
    assert burst(e, "acme:10.0.0.8") == 12


def test_row_effective_before_the_backfill_still_governs_earlier_instants():
    """before the backfilled row's effective_at, the original row still governs."""
    e, _ = limiter(1735689850.0)
    assert burst(e, "acme:10.0.0.6") == 20


def test_scheduled_row_does_not_apply_before_its_effective_at():
    """a future-dated row is inert until its effective_at, however high its revision."""
    e, _ = limiter(1735692100.0)
    assert burst(e, "acme:10.0.0.9") == 12


def test_scheduled_row_applies_once_its_effective_at_has_passed():
    """the same future-dated row governs at instants at or after its effective_at."""
    e, _ = limiter(1735696900.0)
    assert burst(e, "acme:10.0.0.9") == 100


def test_amended_publish_wins_the_effective_at_tie():
    """two rows sharing an effective_at are separated by revision, higher wins."""
    e, _ = limiter(1735691500.0)
    assert burst(e, "globex:10.0.0.21") == 3


def test_row_before_the_amended_publish_governs_earlier_instants():
    """the tied rows are inert before their shared effective_at."""
    e, _ = limiter(1735690500.0)
    assert burst(e, "globex:10.0.0.20") == 9


def test_unknown_tenant_falls_back_to_the_default_row():
    """a tenant absent from the export is governed by the '*' rows."""
    e, _ = limiter(1735691000.0)
    assert burst(e, "zeta:7") == 4


def test_key_with_no_tenant_falls_back_to_the_default_row():
    """a key containing no ':' names no tenant and is governed by the '*' rows."""
    e, _ = limiter(1735691000.0)
    assert burst(e, "healthcheck") == 4


def test_tenant_is_the_text_before_the_first_colon():
    """a client id containing colons of its own does not change the tenant."""
    e, _ = limiter(1735690300.0)
    assert burst(e, "acme:10.0.0.7:443") == 5


def test_tenant_with_no_row_in_force_yet_uses_the_default_row():
    """a tenant whose only row is not yet effective falls back to '*'."""
    e, _ = limiter(1735689950.0)
    assert burst(e, "initech:svc-0") == 4


def test_tenant_row_governs_once_it_is_effective():
    """the same tenant's own row governs from its effective_at on."""
    e, _ = limiter(1735690500.0)
    assert burst(e, "initech:svc-1") == 5


def test_default_row_itself_changes_over_time():
    """the '*' tenant is an ordinary timeline, not a fixed fallback constant."""
    e, _ = limiter(1735689700.0)
    assert burst(e, "zeta:8") == 10


def test_refill_rate_comes_from_the_governing_row():
    """rate as well as capacity is read off the row in force."""
    e, clk = limiter(1735690900.0)
    assert burst(e, "acme:10.0.0.8") == 12
    clk.advance(60)
    assert e.tokens("acme:10.0.0.8") == pytest.approx(3.0)


# ---------------------------------------------- refill across policy edges


def test_refill_integrates_across_one_policy_edge():
    """an idle span straddling an edge is credited per segment, not at one rate."""
    e, clk = limiter(1735690740.0)
    assert e.allow("acme:10.0.0.30", cost=4) is True
    clk.t = 1735690830.0
    assert e.tokens("acme:10.0.0.30") == pytest.approx(3.7)


def test_refill_across_an_upgrade_edge_from_empty():
    """each segment contributes its own elapsed time times its own rate."""
    e, clk = limiter(1735690700.0)
    assert e.allow("acme:10.0.0.33", cost=5) is True
    clk.t = 1735690900.0
    assert e.tokens("acme:10.0.0.33") == pytest.approx(7.0)


def test_refill_across_two_policy_edges():
    """a span crossing two edges is split into three segments."""
    e, clk = limiter(1735689960.0)
    assert e.allow("acme:10.0.0.31", cost=6) is True
    clk.t = 1735690820.0
    assert e.tokens("acme:10.0.0.31") == pytest.approx(6.0)


def test_downgrade_truncation_is_not_undone_by_later_refill():
    """tokens lost to a mid-span capacity cut stay lost after the next upgrade."""
    e, clk = limiter(1735689960.0)
    assert e.allow("acme:10.0.0.32", cost=6) is True
    clk.t = 1735690860.0
    assert e.tokens("acme:10.0.0.32") == pytest.approx(8.0)


def test_bucket_is_not_recreated_when_the_policy_changes():
    """a policy change does not reset a bucket to full at the new capacity."""
    e, clk = limiter(1735690700.0)
    assert e.allow("acme:10.0.0.34", cost=5) is True
    clk.t = 1735690800.0
    assert e.tokens("acme:10.0.0.34") == pytest.approx(2.0)


def test_capacity_cut_truncates_the_bucket_at_the_edge_instant():
    """a probe taken exactly on an edge already sees the new capacity."""
    e, clk = limiter(1735689890.0)
    assert e.tokens("zeta:11") == pytest.approx(10.0)
    clk.t = 1735689900.0
    assert e.tokens("zeta:11") == pytest.approx(4.0)


def test_cost_above_the_effective_capacity_is_denied_and_consumes_nothing():
    """an unsatisfiable cost produces a deny, not an error, a wait or a debit."""
    e, _ = limiter(1735691500.0)
    assert e.tokens("globex:10.0.0.42") == pytest.approx(3.0)
    assert e.allow("globex:10.0.0.42", cost=10) is False
    assert e.tokens("globex:10.0.0.42") == pytest.approx(3.0)


def test_fresh_bucket_is_full_at_the_capacity_in_force_not_the_default():
    """first touch fills the bucket to the governing row's capacity."""
    e, _ = limiter(1735690300.0)
    assert e.tokens("acme:10.0.0.35") == pytest.approx(5.0)


# ------------------------------------------------------ backwards clock


def test_clock_step_backwards_grants_no_tokens():
    """a call earlier than the bucket's anchor credits nothing."""
    clk = Clock(2000.0)
    e = RateLimiterEngine({"capacity": 6, "rate": 1.0, "clock": clk})
    assert e.allow("svc:a", cost=4) is True
    clk.t = 1998.0
    assert e.tokens("svc:a") == pytest.approx(2.0)


def test_refill_anchor_does_not_rewind_on_a_backwards_step():
    """time re-run after a backwards step is not credited a second time."""
    clk = Clock(2000.0)
    e = RateLimiterEngine({"capacity": 6, "rate": 1.0, "clock": clk})
    assert e.allow("svc:a", cost=4) is True
    clk.t = 1998.0
    assert e.tokens("svc:a") == pytest.approx(2.0)
    clk.t = 1999.5
    assert e.tokens("svc:a") == pytest.approx(2.0)


def test_catchup_credits_only_the_span_beyond_the_high_water_mark():
    """once the clock passes the anchor again only the new span is credited."""
    clk = Clock(2000.0)
    e = RateLimiterEngine({"capacity": 6, "rate": 1.0, "clock": clk})
    assert e.allow("svc:a", cost=4) is True
    for when, expected in ((1998.0, 2.0), (1999.5, 2.0), (2002.0, 4.0)):
        clk.t = when
        assert e.tokens("svc:a") == pytest.approx(expected), when


def test_window_prunes_entries_that_are_not_at_the_front():
    """an out-of-order arrival is expired on its own timestamp, not its position."""
    clk = Clock(1000.0)
    e = RateLimiterEngine({"clock": clk})
    assert e.sliding_window("svc:b", 10, 3) is True
    clk.t = 1001.0
    assert e.sliding_window("svc:b", 10, 3) is True
    clk.t = 995.0
    assert e.sliding_window("svc:b", 10, 3) is True
    clk.t = 1005.5
    assert e.sliding_window("svc:b", 10, 3) is True


def test_window_records_the_raw_arrival_time():
    """the timeline logs the clock as observed, not a forward-clamped value."""
    clk = Clock(1000.0)
    e = RateLimiterEngine({"clock": clk})
    assert e.sliding_window("svc:d", 10, 2) is True
    clk.t = 996.0
    assert e.sliding_window("svc:d", 10, 2) is True
    clk.t = 1005.9
    assert e.sliding_window("svc:d", 10, 2) is False
    clk.t = 1006.1
    assert e.sliding_window("svc:d", 10, 2) is True


def test_window_out_of_order_entry_and_window_edge_together():
    """a stranded arrival and an arrival exactly on the edge both expire."""
    clk = Clock(1000.0)
    e = RateLimiterEngine({"clock": clk})
    assert e.sliding_window("svc:c", 10, 3) is True
    clk.t = 1004.0
    assert e.sliding_window("svc:c", 10, 3) is True
    clk.t = 996.0
    assert e.sliding_window("svc:c", 10, 3) is True
    clk.t = 1006.0
    assert e.sliding_window("svc:c", 10, 3) is True


# ------------------------------------------------------- the window edge


def test_window_entry_exactly_on_the_edge_has_expired():
    """an arrival at exactly now - window_sec is outside the window."""
    clk = Clock(1000.0)
    e = RateLimiterEngine({"clock": clk})
    assert e.sliding_window("w:exact", 10, 1) is True
    clk.t = 1010.0
    assert e.sliding_window("w:exact", 10, 1) is True


def test_window_entry_a_hair_inside_the_edge_is_still_counted():
    """an arrival a microsecond newer than the edge is still inside the window."""
    clk = Clock(1000.0)
    e = RateLimiterEngine({"clock": clk})
    assert e.sliding_window("w:hair", 10, 1) is True
    clk.t = 1009.999999
    assert e.sliding_window("w:hair", 10, 1) is False


def test_window_edge_with_several_entries():
    """the edge rule holds when only part of the timeline has aged out."""
    clk = Clock(500.0)
    e = RateLimiterEngine({"clock": clk})
    assert e.sliding_window("w:multi", 20, 2) is True
    clk.t = 505.0
    assert e.sliding_window("w:multi", 20, 2) is True
    clk.t = 520.0
    assert e.sliding_window("w:multi", 20, 2) is True
    clk.t = 524.999999
    assert e.sliding_window("w:multi", 20, 2) is False
    clk.t = 525.0
    assert e.sliding_window("w:multi", 20, 2) is True
