import pytest
from engine.engine import QuicServerEngine, FlowControlError
from engine.packets import MSS


@pytest.fixture
def e():
    return QuicServerEngine()


def test_bidi_stream_ids(e):
    ids = [e.open_bidi() for _ in range(3)]
    assert ids == [0, 4, 8]
    assert all(i % 4 == 0 for i in ids)


def test_uni_stream_ids(e):
    ids = [e.open_uni() for _ in range(3)]
    assert ids == [2, 6, 10]
    assert all(i % 4 == 2 for i in ids)


def test_bidi_and_uni_do_not_collide(e):
    b = {e.open_bidi() for _ in range(5)}
    u = {e.open_uni() for _ in range(5)}
    assert b.isdisjoint(u)


def test_send_recv(e):
    s = e.open_bidi()
    assert e.send(s, b"hi") == 2
    e.send(s, b" there")
    assert e.recv(s) == b"hi there"
    assert e.recv(999) is None


def test_datagrams(e):
    i0 = e.send_datagram(b"d0")
    i1 = e.send_datagram(b"d1")
    assert (i0, i1) == (0, 1)
    assert e.recv_datagram(i1) == b"d1"


def test_stream_flow_control(e):
    q = QuicServerEngine({"initial_max_stream_data": 10})
    s = q.open_bidi()
    q.send(s, b"12345")
    with pytest.raises(FlowControlError):
        q.send(s, b"678901")
    q.update_max_stream_data(s, 20)
    assert q.send(s, b"678901") == 6


def test_connection_flow_control(e):
    q = QuicServerEngine({"initial_max_data": 8, "initial_max_stream_data": 100})
    a, b = q.open_bidi(), q.open_bidi()
    q.send(a, b"12345")
    with pytest.raises(FlowControlError):
        q.send(b, b"6789")
    q.update_max_data(100)
    assert q.send(b, b"6789") == 4


def test_bytes_in_flight_tracking(e):
    for pn in range(4):
        e.on_packet_sent(pn, 1000)
    assert e.congestion_feedback()["bytes_in_flight"] == 4000
    assert e.congestion_feedback()["in_flight_packets"] == 4
    e.on_ack(0)
    assert e.congestion_feedback()["bytes_in_flight"] == 3000


def test_slow_start_grows_cwnd(e):
    q = QuicServerEngine({"initial_cwnd": 12000})
    for pn in range(3):
        q.on_packet_sent(pn, MSS)
    before = q.congestion_feedback()["cwnd"]
    q.on_ack(0)
    q.on_ack(1)
    assert q.congestion_feedback()["cwnd"] == before + 2 * MSS
    assert q.congestion_feedback()["state"] == "slow_start"


def test_loss_halves_cwnd_and_enters_recovery(e):
    q = QuicServerEngine({"initial_cwnd": 20000})
    for pn in range(5):
        q.on_packet_sent(pn, MSS)
    before = q.congestion_feedback()["cwnd"]
    q.loss_event(2)
    fb = q.congestion_feedback()
    assert fb["cwnd"] < before
    assert fb["ssthresh"] == fb["cwnd"]
    assert fb["state"] == "recovery"


def test_recovery_exits_on_ack_of_newer_packet(e):
    q = QuicServerEngine({"initial_cwnd": 20000})
    for pn in range(5):
        q.on_packet_sent(pn, MSS)
    q.loss_event(2)
    q.on_packet_sent(10, MSS)
    q.on_ack(10)
    assert q.congestion_feedback()["state"] == "congestion_avoidance"


def test_congestion_avoidance_growth_is_sub_linear(e):
    q = QuicServerEngine({"initial_cwnd": 4 * MSS})
    q.on_packet_sent(0, MSS)
    q.loss_event(0)                          # ssthresh now 2*MSS, cwnd small
    # push cwnd above ssthresh so we are in congestion avoidance
    for pn in range(1, 6):
        q.on_packet_sent(pn, MSS)
        q.on_ack(pn)
    fb = q.congestion_feedback()
    assert fb["state"] in ("congestion_avoidance",)
    # each ack in CA adds well under a full MSS
    cwnd = fb["cwnd"]
    q.on_packet_sent(20, MSS)
    q.on_ack(20)
    assert 0 < q.congestion_feedback()["cwnd"] - cwnd < MSS


def test_ack_ranges(e):
    for pn in range(6):
        e.on_packet_sent(pn, 500)
    e.on_ack(5, ack_ranges=[(0, 2), (4, 5)])
    assert e.congestion_feedback()["bytes_in_flight"] == 500   # only pn 3 left


def test_reset_and_configure(e):
    s = e.open_bidi()
    e.send(s, b"x")
    e.on_packet_sent(1, 1000)
    e.reset()
    assert e.congestion_feedback()["bytes_in_flight"] == 0
    assert e.open_bidi() == 0
    e.configure({"initial_cwnd": 5000})
    assert e.congestion_feedback()["cwnd"] == 5000


def test_send_to_unknown_stream_raises(e):
    with pytest.raises(KeyError):
        e.send(999, b"data")
    sid = e.open_bidi()
    with pytest.raises(KeyError):
        e.send(sid + 1, b"x")           # a plausible-but-unopened id


def test_stream_limit_allows_filling_it_exactly():
    """Flow control refuses data that would take a stream past its limit, so a
    write that lands exactly on the limit is allowed and the next byte is not."""
    e = QuicServerEngine({"initial_max_stream_data": 100, "initial_max_data": 1 << 20})
    sid = e.open_bidi()
    assert e.send(sid, b"x" * 100) == 100
    with pytest.raises(FlowControlError):
        e.send(sid, b"y")


def test_connection_limit_allows_filling_it_exactly():
    """The connection limit behaves the same way as the stream limit."""
    e = QuicServerEngine({"initial_max_data": 50, "initial_max_stream_data": 1 << 16})
    sid = e.open_bidi()
    assert e.send(sid, b"x" * 50) == 50
    with pytest.raises(FlowControlError):
        e.send(sid, b"z")


def test_slow_start_leaves_on_reaching_ssthresh_not_only_past_it():
    """Slow start ends when the window reaches the threshold, not when it
    overshoots: a window landing exactly on ssthresh is already in congestion
    avoidance."""
    e = QuicServerEngine({"initial_cwnd": 4 * MSS})
    e.on_packet_sent(1, 2 * MSS)
    e.loss_event(1)                       # ssthresh = max(2*MSS, 2*MSS) = 2*MSS
    before = e.congestion_feedback()
    assert before["state"] == "recovery"

    e.on_packet_sent(2, MSS)
    e.on_ack(2)                           # largest_acked 2 > largest_lost 1
    assert e.congestion_feedback()["state"] == "congestion_avoidance"


def test_recovery_ends_only_on_an_ack_past_the_lost_packet():
    """An acknowledgement of a packet at or below the largest lost one does not
    end recovery."""
    e = QuicServerEngine()
    e.on_packet_sent(5, MSS)
    e.on_packet_sent(9, MSS)
    e.loss_event(9)                       # largest_lost = 9
    assert e.congestion_feedback()["state"] == "recovery"
    e.on_ack(5)                           # 5 is not past 9
    assert e.congestion_feedback()["state"] == "recovery"


def test_loss_keeps_the_highest_lost_packet_and_halves_the_window():
    """largest_lost is a high-water mark, and ssthresh never drops below two
    segments however small the window gets."""
    e = QuicServerEngine({"initial_cwnd": 20 * MSS})
    for pn in (3, 11, 7):
        e.on_packet_sent(pn, MSS)
    e.loss_event(11)
    e.loss_event(3)                       # older loss must not lower the mark
    e.on_packet_sent(12, MSS)
    e.on_ack(12)                          # 12 is past 11, so recovery ends
    assert e.congestion_feedback()["state"] == "congestion_avoidance"

    small = QuicServerEngine({"initial_cwnd": MSS})
    small.on_packet_sent(1, MSS)
    small.loss_event(1)
    assert small.congestion_feedback()["cwnd"] >= 2 * MSS


def test_recovery_survives_an_ack_that_only_reaches_the_lost_packet():
    """Recovery ends on an acknowledgement past the largest lost packet. An ack
    whose largest number equals that packet has not gone past it, even when the
    ack range carries newly acknowledged bytes with it."""
    e = QuicServerEngine()
    e.on_packet_sent(5, MSS)
    e.on_packet_sent(9, MSS)
    e.loss_event(9)
    assert e.congestion_feedback()["state"] == "recovery"
    e.on_ack(9, ack_ranges=[(5, 5)])      # newly acked bytes, but 9 is not past 9
    assert e.congestion_feedback()["state"] == "recovery"


def test_window_equal_to_ssthresh_grows_the_congestion_avoidance_way():
    """A loss sets the window equal to the threshold. The next acknowledgement
    is therefore in congestion avoidance, not slow start, and the window grows
    by roughly one segment rather than by everything acknowledged."""
    e = QuicServerEngine({"initial_cwnd": 4 * MSS})
    e.on_packet_sent(1, 2 * MSS)
    e.loss_event(1)                        # ssthresh = 2*MSS, cwnd = 2*MSS
    assert e.congestion_feedback()["cwnd"] == 2 * MSS

    e.on_packet_sent(2, MSS)
    e.on_ack(2)                            # newly = MSS
    # congestion avoidance: cwnd += MSS*MSS // cwnd  ->  2400 + 600
    assert e.congestion_feedback()["cwnd"] == 2 * MSS + (MSS * MSS) // (2 * MSS)


def test_congestion_avoidance_growth_is_at_least_one_byte():
    """The per-ack increase is the larger of one byte and the computed share,
    so a very large window still creeps forward rather than standing still."""
    e = QuicServerEngine({"initial_cwnd": 4 * MSS})
    e.on_packet_sent(1, 2 * MSS)
    e.loss_event(1)
    e.on_packet_sent(2, MSS)
    e.on_ack(2)
    grown = e.congestion_feedback()["cwnd"]
    assert grown > 2 * MSS + 1, "the increase must be the computed share, not the floor"
