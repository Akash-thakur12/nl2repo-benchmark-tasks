import pytest
from engine.engine import TorRelayEngine
from engine.cells import CELL_PAYLOAD_LEN


def test_single_hop_roundtrip():
    e = TorRelayEngine()
    e.register_circuit(7, 0, b"k" * 16)
    cell = e.make_cell(7, 0, b"hello world")
    assert len(cell) == CELL_PAYLOAD_LEN
    assert e.decrypt(7, 0, cell) == b"OKhello world"
    assert e.recognized(7, 0) is True


def test_unknown_circuit_returns_none():
    e = TorRelayEngine()
    assert e.decrypt(99, 0, b"x" * CELL_PAYLOAD_LEN) is None
    assert e.recognized(99, 0) is False


def test_garbage_is_not_recognized():
    e = TorRelayEngine()
    e.register_circuit(1, 0, b"k" * 16)
    assert e.decrypt(1, 0, b"x" * CELL_PAYLOAD_LEN) is None
    assert e.recognized(1, 0) is False


def test_wrong_key_does_not_recognize():
    e = TorRelayEngine()
    e.register_circuit(1, 0, b"a" * 16)
    cell = e.make_cell(1, 0, b"payload")
    e.register_circuit(1, 0, b"b" * 16)          # key rotated
    assert e.decrypt(1, 0, cell) is None
    assert e.recognized(1, 0) is False


def test_make_cell_without_key_raises():
    e = TorRelayEngine()
    with pytest.raises(ValueError):
        e.make_cell(5, 0, b"x")


def test_payload_too_large_raises():
    e = TorRelayEngine()
    e.register_circuit(1, 0, b"k" * 16)
    with pytest.raises(ValueError):
        e.make_cell(1, 0, b"a" * CELL_PAYLOAD_LEN)


@pytest.mark.parametrize("payload", [b"", b"a", b"a" * 100, b"a" * 480,
                                     bytes(range(256)) * 1])
def test_roundtrip_matrix(payload):
    e = TorRelayEngine()
    e.register_circuit(1, 0, b"k" * 16)
    cell = e.make_cell(1, 0, payload)
    assert len(cell) == CELL_PAYLOAD_LEN
    assert e.decrypt(1, 0, cell) == b"OK" + payload


def test_multi_hop_onion_wrap_and_peel():
    e = TorRelayEngine()
    for h in range(3):
        e.register_circuit(1, h, bytes([h + 1]) * 32)
    onion = e.make_onion(1, [0, 1, 2], b"secret message")
    assert len(onion) == CELL_PAYLOAD_LEN
    assert e.peel(1, [0, 1, 2], onion) == b"OKsecret message"
    assert e.recognized(1, 2) is True


def test_peel_with_wrong_path_fails():
    e = TorRelayEngine()
    for h in range(3):
        e.register_circuit(1, h, bytes([h + 1]) * 32)
    onion = e.make_onion(1, [0, 1, 2], b"msg")
    assert e.peel(1, [0, 1], onion) is None          # stopped one hop short (missing hop 2 key layer)
    e2 = TorRelayEngine()
    for h in range(3):
        e2.register_circuit(1, h, bytes([9]) * 32)   # all wrong keys
    assert e2.peel(1, [0, 1, 2], onion) is None


def test_two_hop_onion():
    e = TorRelayEngine()
    e.register_circuit(9, 0, b"x" * 24)
    e.register_circuit(9, 1, b"y" * 24)
    onion = e.make_onion(9, [0, 1], b"abc")
    assert e.peel(9, [0, 1], onion) == b"OKabc"


def test_reset_clears_recognized_set():
    e = TorRelayEngine()
    e.register_circuit(1, 0, b"k" * 16)
    e.decrypt(1, 0, e.make_cell(1, 0, b"x"))
    assert e.recognized(1, 0) is True
    e.reset()
    assert e.recognized(1, 0) is False


def test_configure_clears_keys_and_recognized():
    e = TorRelayEngine()
    e.register_circuit(1, 0, b"k" * 16)
    e.decrypt(1, 0, e.make_cell(1, 0, b"x"))
    e.configure({})
    assert e.recognized(1, 0) is False
    with pytest.raises(ValueError):
        e.make_cell(1, 0, b"x")


def test_deterministic():
    e = TorRelayEngine()
    e.register_circuit(1, 0, b"k" * 16)
    a = e.make_cell(1, 0, b"same")
    b = e.make_cell(1, 0, b"same")
    assert a == b


def test_payload_of_exactly_the_maximum_size_is_accepted():
    """A cell has room for CELL_PAYLOAD_LEN bytes less the marker and the
    length field. A payload of exactly that size is the largest one that fits,
    so it must be accepted and must survive the round trip."""
    from engine.cells import CELL_PAYLOAD_LEN, LEN_FIELD, RECOGNIZED_MARKER

    e = TorRelayEngine()
    e.register_circuit(7, 0, b"k" * 16)
    biggest = CELL_PAYLOAD_LEN - len(RECOGNIZED_MARKER) - LEN_FIELD
    payload = bytes(range(256)) * (biggest // 256) + b"z" * (biggest % 256)
    assert len(payload) == biggest

    cell = e.make_cell(7, 0, payload)
    assert len(cell) == CELL_PAYLOAD_LEN
    assert e.decrypt(7, 0, cell) == RECOGNIZED_MARKER + payload

    with pytest.raises(ValueError):
        e.make_cell(7, 0, payload + b"!")


def test_payload_reaching_the_end_of_the_cell_is_not_rejected():
    """The length check on the way out is on the end of the payload running
    past the cell, not on it reaching the last byte. A payload that ends
    exactly on the final byte is still recognized."""
    from engine.cells import CELL_PAYLOAD_LEN, LEN_FIELD, RECOGNIZED_MARKER

    e = TorRelayEngine()
    e.register_circuit(8, 0, b"k" * 16)
    biggest = CELL_PAYLOAD_LEN - len(RECOGNIZED_MARKER) - LEN_FIELD
    payload = b"\xa5" * biggest

    peeled = e.decrypt(8, 0, e.make_cell(8, 0, payload))
    assert peeled is not None
    assert peeled == RECOGNIZED_MARKER + payload
    assert e.recognized(8, 0) is True
