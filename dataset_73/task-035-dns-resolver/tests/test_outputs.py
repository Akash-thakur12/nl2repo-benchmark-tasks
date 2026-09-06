import struct

import pytest
from engine.engine import DnsResolverEngine
from engine.messages import TYPE_A, TYPE_AAAA, TYPE_CNAME, TYPE_MX, TYPE_SOA


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


@pytest.fixture
def e():
    return DnsResolverEngine()


def test_encode_parse_name_roundtrip(e):
    for name in ["a", "a.b", "a.b.c", "www.example.com", "x.y.z.example.com"]:
        blob = e.encode_name(name)
        got, off = e.parse_name(blob, 0)
        assert got == name + "." and off == len(blob)


def test_parse_name_offset_past_pointer(e):
    packet = b"\x00" * 12 + e.encode_name("host.example") + b"\xc0\x0c"
    ptr_at = len(packet) - 2
    name, off = e.parse_name(packet, ptr_at)
    assert name == "host.example." and off == ptr_at + 2


def test_parse_name_pointer_loop_raises(e):
    packet = b"\xc0\x00" + b"\x00" * 10
    with pytest.raises(ValueError):
        e.parse_name(packet, 0)


def test_parse_short_packet_raises(e):
    with pytest.raises(ValueError):
        e.parse(b"\x00\x00")


def test_parse_response_a_record(e):
    qname = e.encode_name("a.b")
    ans = bytes([0xC0, 0x0C]) + struct.pack(">HHIH", TYPE_A, 1, 60, 4) + bytes([1, 2, 3, 4])
    blob = struct.pack(">HHHHHH", 0xABCD, 0x8180, 1, 1, 0, 0) + qname \
        + struct.pack(">HH", TYPE_A, 1) + ans
    r = e.parse(blob)
    assert r["id"] == 0xABCD
    assert r["flags"]["qr"] is True and r["flags"]["ra"] is True
    a = r["answers"][0]
    assert a["type"] == TYPE_A and a["type_name"] == "A" and a["address"] == "1.2.3.4"


def test_parse_response_mx_record(e):
    qname = e.encode_name("x.com")
    rd = struct.pack(">H", 10) + bytes([4]) + b"mail" + bytes([0])
    ans = bytes([0xC0, 0x0C]) + struct.pack(">HHIH", TYPE_MX, 1, 300, len(rd)) + rd
    blob = struct.pack(">HHHHHH", 1, 0x8180, 1, 1, 0, 0) + qname \
        + struct.pack(">HH", TYPE_MX, 1) + ans
    a = e.parse(blob)["answers"][0]
    assert a["preference"] == 10 and a["exchange"] == "mail."


def test_parse_response_cname(e):
    qname = e.encode_name("www.x.com")
    rd = bytes([3]) + b"lb1" + bytes([1]) + b"x" + bytes([3]) + b"com" + bytes([0])
    ans = bytes([0xC0, 0x0C]) + struct.pack(">HHIH", TYPE_CNAME, 1, 120, len(rd)) + rd
    blob = struct.pack(">HHHHHH", 2, 0x8180, 1, 1, 0, 0) + qname \
        + struct.pack(">HH", TYPE_CNAME, 1) + ans
    a = e.parse(blob)["answers"][0]
    assert a["type_name"] == "CNAME" and a["target"] == "lb1.x.com."


def test_parse_aaaa(e):
    qname = e.encode_name("v6.example")
    addr = bytes(range(16))
    ans = bytes([0xC0, 0x0C]) + struct.pack(">HHIH", TYPE_AAAA, 1, 60, 16) + addr
    blob = struct.pack(">HHHHHH", 3, 0x8180, 1, 1, 0, 0) + qname \
        + struct.pack(">HH", TYPE_AAAA, 1) + ans
    a = e.parse(blob)["answers"][0]
    assert a["address"] == "0001:0203:0405:0607:0809:0a0b:0c0d:0e0f"


def test_encode_query_roundtrips(e):
    q = e.encode("example.com", TYPE_A, 0x4242)
    r = e.parse(q)
    assert r["id"] == 0x4242 and r["flags"]["qr"] is False and r["flags"]["rd"] is True
    assert r["questions"][0] == {"name": "example.com.", "type": TYPE_A, "class": 1}


def test_cache_is_keyed_on_name_and_type():
    clk = Clock()
    e = DnsResolverEngine({"clock": clk})
    e.cache_put("x.com", TYPE_A, ["1.2.3.4"], ttl=60)
    e.cache_put("x.com", TYPE_AAAA, ["::1"], ttl=60)
    assert e.cache_get("x.com", TYPE_A) == ["1.2.3.4"]
    assert e.cache_get("x.com", TYPE_AAAA) == ["::1"]
    assert e.cache_get("x.com", TYPE_MX) is None
    assert e.cache_get("y.com", TYPE_A) is None


def test_cache_ttl_expiry():
    clk = Clock()
    e = DnsResolverEngine({"clock": clk})
    e.cache_put("x.com", TYPE_A, ["1.2.3.4"], ttl=30)
    clk.advance(29)
    assert e.cache_get("x.com", TYPE_A) == ["1.2.3.4"]
    clk.advance(2)
    assert e.cache_get("x.com", TYPE_A) is None


def test_validate_dnssec_stub(e):
    assert e.validate_dnssec({"flags": {"ad": True}}) == "secure"
    assert e.validate_dnssec({"flags": {"ad": False}}) == "insecure"
    assert e.validate_dnssec({}) == "insecure"


def test_reset_and_configure_clear_cache():
    e = DnsResolverEngine()
    e.cache_put("x.com", TYPE_A, ["1"], ttl=999)
    e.reset()
    assert e.cache_get("x.com", TYPE_A) is None
    e.cache_put("x.com", TYPE_A, ["1"], ttl=999)
    e.configure({})
    assert e.cache_get("x.com", TYPE_A) is None


@pytest.mark.parametrize("name", ["a", "a.b", "a.b.c", "x.y.z.example.com"])
def test_name_matrix(e, name):
    enc = e.encode_name(name)
    got, _ = e.parse_name(enc, 0)
    assert got == name + "."


def _answer(qname_wire, rtype, rdata, ttl=300):
    return bytes([0xC0, 0x0C]) + struct.pack(">HHIH", rtype, 1, ttl, len(rdata)) + rdata


def _response(e, name, rtype, rdata):
    q = e.encode_name(name)
    return (struct.pack(">HHHHHH", 0x1234, 0x8180, 1, 1, 0, 0)
            + q + struct.pack(">HH", rtype, 1) + _answer(q, rtype, rdata))


def test_parse_ns_record(e):
    from engine.messages import TYPE_NS
    rd = bytes([3]) + b"ns1" + bytes([1]) + b"x" + bytes([0])
    a = e.parse(_response(e, "x", TYPE_NS, rd))["answers"][0]
    assert a["type_name"] == "NS" and a["target"] == "ns1.x."


def test_parse_soa_record(e):
    from engine.messages import TYPE_SOA
    rd = (bytes([2]) + b"ns" + bytes([1]) + b"x" + bytes([0])
          + bytes([4]) + b"root" + bytes([1]) + b"x" + bytes([0])
          + struct.pack(">IIIII", 2024010101, 7200, 3600, 1209600, 86400))
    a = e.parse(_response(e, "x", TYPE_SOA, rd))["answers"][0]
    assert a["type_name"] == "SOA"
    assert a["mname"] == "ns.x." and a["rname"] == "root.x."
    assert a["serial"] == 2024010101 and a["minimum"] == 86400
    assert a["refresh"] == 7200 and a["retry"] == 3600 and a["expire"] == 1209600


def test_parse_txt_record(e):
    from engine.messages import TYPE_TXT
    rd = bytes([11]) + b"hello world"
    a = e.parse(_response(e, "x", TYPE_TXT, rd))["answers"][0]
    assert a["type_name"] == "TXT" and a["text"] == "hello world"


def test_aaaa_address_format(e):
    from engine.messages import TYPE_AAAA
    a = e.parse(_response(e, "v6", TYPE_AAAA, bytes(range(16))))["answers"][0]
    assert a["address"] == "0001:0203:0405:0607:0809:0a0b:0c0d:0e0f"


def test_parse_name_runs_off_end_raises(e):
    # a label claiming length 5 with only 2 bytes of data left, no terminator
    with pytest.raises(ValueError):
        e.parse_name(b"\x05ab", 0)


def test_parse_rdata_truncated_raises(e):
    qname = e.encode_name("x.com")
    # answer header says rdlen=10 but only 2 rdata bytes follow
    ans = bytes([0xC0, 0x0C]) + struct.pack(">HHIH", TYPE_A, 1, 60, 10) + b"\x01\x02"
    blob = (struct.pack(">HHHHHH", 1, 0x8180, 1, 1, 0, 0) + qname
            + struct.pack(">HH", TYPE_A, 1) + ans)
    with pytest.raises(ValueError):
        e.parse(blob)


def test_parse_all_four_valueerror_conditions(e):
    # 1. packet shorter than the 12-byte header
    with pytest.raises(ValueError):
        e.parse(b"\x00" * 5)
    # 2. rdata truncated  (covered above, re-assert compactly)
    q = e.encode_name("a")
    bad_rd = (struct.pack(">HHHHHH", 1, 0x8180, 1, 1, 0, 0) + q
              + struct.pack(">HH", TYPE_A, 1)
              + bytes([0xC0, 0x0C]) + struct.pack(">HHIH", TYPE_A, 1, 0, 8) + b"\x00")
    with pytest.raises(ValueError):
        e.parse(bad_rd)
    # 3. compression pointer loop
    with pytest.raises(ValueError):
        e.parse_name(b"\xc0\x00" + b"\x00" * 8, 0)
    # 4. name runs past the end of the buffer
    with pytest.raises(ValueError):
        e.parse_name(b"\x08abc", 0)


def test_a_bare_header_is_long_enough(e):
    """The header is twelve bytes. A packet of exactly twelve is a header with
    no sections, not a truncated packet; eleven is truncated."""
    header = struct.pack(">HHHHHH", 0x1234, 0x8180, 0, 0, 0, 0)
    r = e.parse(header)
    assert r["id"] == 0x1234 and r["questions"] == []

    with pytest.raises(ValueError):
        e.parse(header[:11])


def test_a_name_that_starts_at_the_end_is_a_clean_error(e):
    """Running out of buffer while reading a name is reported, not left to
    blow up on an index."""
    with pytest.raises(ValueError):
        e.parse_name(b"\x03www", 4)


def test_a_cache_entry_expires_the_moment_it_is_due(e):
    """The time-to-live is how long the entry is good for, so it is already
    gone at the instant it expires, not one tick later."""
    clock = Clock(1000.0)
    e.configure({"clock": clock})
    e.cache_put("example.com.", TYPE_A, [{"address": "1.2.3.4"}], ttl=10)

    clock.t = 1009.999
    assert e.cache_get("example.com.", TYPE_A) is not None
    clock.t = 1010.0
    assert e.cache_get("example.com.", TYPE_A) is None


def test_configure_with_an_empty_options_object_keeps_the_clock(e):
    """An empty options object is a real object and must be handled the same
    way as none at all - neither replaces the clock."""
    clock = Clock(500.0)
    e.configure({"clock": clock})
    e.configure({})
    e.cache_put("a.", TYPE_A, [{"address": "9.9.9.9"}], ttl=5)
    clock.t = 504.0
    assert e.cache_get("a.", TYPE_A) is not None
    clock.t = 505.0
    assert e.cache_get("a.", TYPE_A) is None


def _packet_with_answer(rtype, rdata):
    header = struct.pack(">HHHHHH", 1, 0x8180, 0, 1, 0, 0)
    name = b"\x02ns\x00"
    rr = name + struct.pack(">HHIH", rtype, 1, 60, len(rdata)) + rdata
    return header + rr


def test_address_records_need_the_right_length(e):
    """An A record is four bytes and a AAAA is sixteen. The type alone does not
    make a record decodable, and neither does the length."""
    short_a = e.parse(_packet_with_answer(TYPE_A, b"\x01\x02\x03"))["answers"][0]
    assert "address" not in short_a

    short_aaaa = e.parse(_packet_with_answer(TYPE_AAAA, b"\x00" * 15))["answers"][0]
    assert "address" not in short_aaaa

    wrong_type_right_length = e.parse(
        _packet_with_answer(9999, b"\x01\x02\x03\x04"))["answers"][0]
    assert "address" not in wrong_type_right_length


def test_an_empty_text_record_decodes_to_nothing(e):
    """A TXT record with no bytes at all carries no text, and a record of some
    other type with bytes in it is not text either."""
    from engine.messages import TYPE_TXT
    empty = e.parse(_packet_with_answer(TYPE_TXT, b""))["answers"][0]
    assert "text" not in empty

    not_txt = e.parse(_packet_with_answer(9998, b"\x03abc"))["answers"][0]
    assert "text" not in not_txt
