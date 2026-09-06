from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class DnsResolverEngine:
    """RFC 1035 DNS parsing + (qname, qtype)-keyed TTL cache. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def encode_name(self, domain):
        raise NotImplementedError(_STUB)

    def parse_name(self, buf, offset):
        raise NotImplementedError(_STUB)

    def encode(self, qname, qtype=1, qid=0x1234, rd=True):
        raise NotImplementedError(_STUB)

    def parse(self, packet):
        raise NotImplementedError(_STUB)

    def cache_put(self, qname, qtype, records, ttl=300):
        raise NotImplementedError(_STUB)

    def cache_get(self, qname, qtype):
        raise NotImplementedError(_STUB)

    def validate_dnssec(self, response):
        raise NotImplementedError(_STUB)
