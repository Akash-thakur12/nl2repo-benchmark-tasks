"""RFC 1035 DNS message parsing + a TTL cache keyed on (qname, qtype)."""
from __future__ import annotations

import time

from engine.messages import (
    TYPE_A, TYPE_AAAA, TYPE_CNAME, TYPE_MX, TYPE_NAMES, TYPE_NS, TYPE_SOA, TYPE_TXT,
)


class DnsResolverEngine:
    def __init__(self, config=None):
        cfg = config or {}
        self._clock = cfg.get("clock", time.time)
        self._cache = {}

    def reset(self):
        self._cache = {}

    def configure(self, options):
        options = options or {}
        self._clock = options.get("clock", self._clock)
        self._cache = {}

    # --------------------------------------------------------------- names
    def encode_name(self, domain):
        out = bytearray()
        for label in domain.strip(".").split("."):
            if label:
                out.append(len(label))
                out += label.encode("ascii")
        out.append(0)
        return bytes(out)

    def parse_name(self, buf, offset):
        """Return (name, next_offset). next_offset is the position in *buf*
        immediately after the name at `offset` (past the 2-byte pointer when
        compression was used)."""
        labels = []
        i = offset
        after = None
        seen_ptr = 0
        while True:
            if i >= len(buf):
                raise ValueError("name runs past end of buffer")
            length = buf[i]
            if length == 0:
                i += 1
                break
            if length & 0xC0 == 0xC0:
                ptr = ((length & 0x3F) << 8) | buf[i + 1]
                if after is None:
                    after = i + 2
                i = ptr
                seen_ptr += 1
                if seen_ptr > 128:
                    raise ValueError("compression pointer loop")
                continue
            i += 1
            labels.append(buf[i:i + length].decode("ascii"))
            i += length
        return ".".join(labels) + ".", (after if after is not None else i)

    # -------------------------------------------------------------- packets
    def encode(self, qname, qtype=TYPE_A, qid=0x1234, rd=True):
        header = qid.to_bytes(2, "big")
        header += (0x0100 if rd else 0x0000).to_bytes(2, "big")
        header += (1).to_bytes(2, "big") + b"\x00\x00" * 3
        return header + self.encode_name(qname) + qtype.to_bytes(2, "big") + b"\x00\x01"

    def parse(self, packet):
        if len(packet) < 12:
            raise ValueError("packet shorter than the 12-byte header")
        qid = int.from_bytes(packet[:2], "big")
        raw_flags = int.from_bytes(packet[2:4], "big")
        flags = {
            "qr": bool(raw_flags & 0x8000),
            "opcode": (raw_flags >> 11) & 0xF,
            "aa": bool(raw_flags & 0x0400),
            "tc": bool(raw_flags & 0x0200),
            "rd": bool(raw_flags & 0x0100),
            "ra": bool(raw_flags & 0x0080),
            "ad": bool(raw_flags & 0x0020),
            "cd": bool(raw_flags & 0x0010),
            "rcode": raw_flags & 0xF,
        }
        counts = [int.from_bytes(packet[i:i + 2], "big") for i in (4, 6, 8, 10)]
        off = 12
        questions = []
        for _ in range(counts[0]):
            name, off = self.parse_name(packet, off)
            qtype = int.from_bytes(packet[off:off + 2], "big")
            qclass = int.from_bytes(packet[off + 2:off + 4], "big")
            off += 4
            questions.append({"name": name, "type": qtype, "class": qclass})

        def read_rrs(n, start):
            rrs = []
            o = start
            for _ in range(n):
                name, o = self.parse_name(packet, o)
                rtype = int.from_bytes(packet[o:o + 2], "big")
                rclass = int.from_bytes(packet[o + 2:o + 4], "big")
                ttl = int.from_bytes(packet[o + 4:o + 8], "big")
                rdlen = int.from_bytes(packet[o + 8:o + 10], "big")
                o += 10
                rdata = packet[o:o + rdlen]
                if len(rdata) < rdlen:
                    raise ValueError("rdata truncated")
                rr = {"name": name, "type": rtype,
                      "type_name": TYPE_NAMES.get(rtype, str(rtype)),
                      "class": rclass, "ttl": ttl, "rdata": rdata}
                rr.update(self._decode_rdata(rtype, rdata, packet, o))
                rrs.append(rr)
                o += rdlen
            return rrs, o

        answers, off = read_rrs(counts[1], off)
        authority, off = read_rrs(counts[2], off)
        additional, off = read_rrs(counts[3], off)
        return {
            "id": qid, "flags": flags, "questions": questions,
            "answers": answers, "authority": authority, "additional": additional,
        }

    def _decode_rdata(self, rtype, rdata, packet, rdata_off):
        if rtype == TYPE_A and len(rdata) == 4:
            return {"address": ".".join(str(b) for b in rdata)}
        if rtype == TYPE_AAAA and len(rdata) == 16:
            groups = [f"{rdata[i]:02x}{rdata[i+1]:02x}" for i in range(0, 16, 2)]
            return {"address": ":".join(groups)}
        if rtype in (TYPE_CNAME, TYPE_NS):
            target, _ = self.parse_name(packet, rdata_off)
            return {"target": target}
        if rtype == TYPE_MX:
            pref = int.from_bytes(rdata[:2], "big")
            exch, _ = self.parse_name(packet, rdata_off + 2)
            return {"preference": pref, "exchange": exch}
        if rtype == TYPE_SOA:
            mname, o = self.parse_name(packet, rdata_off)
            rname, o = self.parse_name(packet, o)
            serial, refresh, retry, expire, minimum = (
                int.from_bytes(packet[o + k:o + k + 4], "big") for k in range(0, 20, 4)
            )
            return {"mname": mname, "rname": rname, "serial": serial,
                    "refresh": refresh, "retry": retry, "expire": expire,
                    "minimum": minimum}
        if rtype == TYPE_TXT and rdata:
            return {"text": rdata[1:1 + rdata[0]].decode("ascii", "replace")}
        return {}

    # --------------------------------------------------------------- cache
    def cache_put(self, qname, qtype, records, ttl=300):
        self._cache[(qname, qtype)] = (records, self._clock() + ttl)

    def cache_get(self, qname, qtype):
        entry = self._cache.get((qname, qtype))
        if entry is None:
            return None
        records, expiry = entry
        if self._clock() >= expiry:
            del self._cache[(qname, qtype)]
            return None
        return records

    # ------------------------------------------------------------- dnssec
    def validate_dnssec(self, response):
        """Stub validator: 'secure' iff the response has the AD (authenticated
        data) bit set, else 'insecure'."""
        return "secure" if response.get("flags", {}).get("ad") else "insecure"
