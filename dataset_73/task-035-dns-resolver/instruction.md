# DNS Packet Dissector & TTL Cache (RFC 1035)

## 1. Overview

Encode / parse DNS wire messages and cache records with a TTL. Standard library
only; code in `engine/`. `engine/messages.py` holds the record-type constants
(`TYPE_A`, `TYPE_NS`, `TYPE_CNAME`, `TYPE_SOA`, `TYPE_MX`, `TYPE_TXT`,
`TYPE_AAAA`) and `TYPE_NAMES`.

## 2. Public API — `engine/engine.py`

### `class DnsResolverEngine`

- `__init__(self, config=None)` — `config["clock"]` is a zero-arg callable
  returning seconds (default `time.time`).
- `encode_name(self, domain: str) -> bytes` — length-prefixed labels + a
  terminating `0`.
- `parse_name(self, buf: bytes, offset: int) -> (str, int)` — the dotted name
  (with trailing `.`) and `next_offset`: the position in `buf` **immediately
  after the name**, which is *past the 2-byte compression pointer* when one was
  followed. Raises `ValueError` on a pointer loop or a name running off the end.
- `encode(self, qname, qtype=TYPE_A, qid=0x1234, rd=True) -> bytes` — a complete
  single-question query packet.
- `parse(self, packet: bytes) -> dict` — raises `ValueError` if shorter than 12
  bytes or an rdata is truncated. Returns:
  ```python
  {
    "id": int,
    "flags": {"qr","opcode","aa","tc","rd","ra","ad","cd","rcode"},
    "questions": [{"name","type","class"}],
    "answers":   [rr, ...], "authority": [rr, ...], "additional": [rr, ...],
  }
  ```
  Each `rr` has `name`, `type`, `type_name`, `class`, `ttl`, `rdata` (raw bytes)
  plus decoded fields:
  - **A** -> `address` as dotted-decimal IPv4 (`"1.2.3.4"`).
  - **AAAA** -> `address` as **eight lowercase 4-hex-digit groups joined by
    `:`** with no `::` compression and no leading-zero trimming
    (e.g. `"0001:0203:0405:0607:0809:0a0b:0c0d:0e0f"`).
  - **CNAME / NS** -> `target` (dotted name with trailing `.`).
  - **MX** -> `preference` (int) + `exchange` (name).
  - **SOA** -> `mname`, `rname`, `serial`, `refresh`, `retry`, `expire`,
    `minimum`.
  - **TXT** -> `text` (the first character-string, ASCII).
- `cache_put(self, qname, qtype, records, ttl=300)` — store under the
  `(qname, qtype)` key with expiry `clock() + ttl`.
- `cache_get(self, qname, qtype)` — the stored `records`, or `None` if absent or
  expired (an expired entry is evicted). Different `qtype`s for one name do not
  collide.
- `validate_dnssec(self, response: dict) -> str` — stub: `"secure"` iff
  `response["flags"]["ad"]` is truthy, else `"insecure"`.
- `reset(self)` / `configure(self, options)` — clear the cache.

## 3. Example

```python
d = DnsResolverEngine()
wire = d.encode_name("example.com")
name, off = d.parse_name(wire, 0)     # -> ("example.com.", len(wire))
d.cache_put("example.com.", TYPE_A, ["93.184.216.34"], ttl=60)
d.cache_get("example.com.", TYPE_A)   # -> ["93.184.216.34"]
```

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
