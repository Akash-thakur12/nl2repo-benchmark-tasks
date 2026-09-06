from __future__ import annotations

import hashlib

from engine.parser import TLS_HANDSHAKE_CLIENT_HELLO, TLS_RECORD_HANDSHAKE

EXT_SUPPORTED_GROUPS = 0x000A     # "elliptic_curves"
EXT_EC_POINT_FORMATS = 0x000B

#: RFC 8701 reserved ("GREASE") values.  They are placeholders a client sends to
#: keep middleboxes honest; they carry no meaning and are excluded from every
#: 16-bit list field of the fingerprint (cipher suites, extension types,
#: supported groups).  EC point formats are 8-bit values and can never be one of
#: these, so that field is never filtered.
GREASE_VALUES = frozenset(
    (n << 8) | n for n in (0x0A, 0x1A, 0x2A, 0x3A, 0x4A, 0x5A, 0x6A, 0x7A,
                           0x8A, 0x9A, 0xAA, 0xBA, 0xCA, 0xDA, 0xEA, 0xFA)
)


class ValidationError(ValueError):
    pass


def _u16(buf, off):
    if off + 2 > len(buf):
        raise ValidationError("truncated: need 2 bytes at offset %d" % off)
    return (buf[off] << 8) | buf[off + 1]


def _u8(buf, off):
    if off + 1 > len(buf):
        raise ValidationError("truncated: need 1 byte at offset %d" % off)
    return buf[off]


def _slice(buf, off, length):
    if off + length > len(buf):
        raise ValidationError("truncated: need %d bytes at offset %d" % (length, off))
    return buf[off:off + length]


class TlsFingerprintEngine:
    """Parse a TLS ClientHello record stream and compute a simplified JA3."""

    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    # -- record layer -----------------------------------------------------
    @staticmethod
    def _reassemble(blob):
        """Concatenate the payloads of the leading handshake records.

        A single handshake message may be split across several records of the
        same content type; the capture is the raw byte stream, so the message
        has to be put back together before it can be parsed.  Record-layer
        versions of the individual fragments are transport artefacts and are
        discarded here.
        """
        payload = bytearray()
        off = 0
        while off + 5 <= len(blob) and blob[off] == TLS_RECORD_HANDSHAKE:
            rec_len = (blob[off + 3] << 8) | blob[off + 4]
            payload += blob[off + 5:off + 5 + rec_len]
            off += 5 + rec_len
        return bytes(payload)

    def parse(self, raw):
        blob = bytes.fromhex(raw) if isinstance(raw, str) else bytes(raw)
        if len(blob) < 5 or blob[0] != TLS_RECORD_HANDSHAKE:
            raise ValidationError("not a TLS handshake record")

        hs = self._reassemble(blob)
        if not hs or hs[0] != TLS_HANDSHAKE_CLIENT_HELLO:
            raise ValidationError("not a ClientHello")

        hs_len = (hs[1] << 16) | (hs[2] << 8) | hs[3]
        body = hs[4:4 + hs_len]

        # The fingerprint's version field comes from the handshake body.
        version = _u16(body, 0)
        i = 2 + 32                                   # client_version, random

        sid_len = _u8(body, i)
        i += 1 + sid_len

        cs_len = _u16(body, i)
        i += 2
        cs_blob = _slice(body, i, cs_len)
        ciphers = [(cs_blob[j] << 8) | cs_blob[j + 1] for j in range(0, cs_len - 1, 2)]
        i += cs_len

        cm_len = _u8(body, i)
        i += 1 + cm_len

        ext_order = []
        ext_data = {}
        if i + 2 <= len(body):
            ext_total = _u16(body, i)
            i += 2
            if i + ext_total > len(body):
                raise ValidationError("extension block runs past the handshake")
            end = i + ext_total
            while i + 4 <= end:
                etype = _u16(body, i)
                elen = _u16(body, i + 2)
                i += 4
                if i + elen > end:
                    raise ValidationError("extension data runs past the block")
                ext_order.append(etype)
                ext_data.setdefault(etype, body[i:i + elen])
                i += elen

        curves = []
        if EXT_SUPPORTED_GROUPS in ext_data:
            data = ext_data[EXT_SUPPORTED_GROUPS]
            n = _u16(data, 0)
            if 2 + n > len(data):
                raise ValidationError("supported_groups runs past its extension")
            curves = [(data[2 + j] << 8) | data[3 + j] for j in range(0, n - 1, 2)]
        point_formats = []
        if EXT_EC_POINT_FORMATS in ext_data:
            data = ext_data[EXT_EC_POINT_FORMATS]
            if data:
                point_formats = list(data[1:1 + data[0]])

        ciphers = [c for c in ciphers if c not in GREASE_VALUES]
        extensions = [e for e in ext_order if e not in GREASE_VALUES]
        curves = [c for c in curves if c not in GREASE_VALUES]

        ja3 = ",".join([
            str(version),
            "-".join(str(c) for c in ciphers) or "0",
            "-".join(str(e) for e in extensions) or "0",
            "-".join(str(c) for c in curves) or "0",
            "-".join(str(p) for p in point_formats) or "0",
        ])
        return {
            "version": version,
            "ciphers": ciphers,
            "extensions": extensions,
            "curves": curves,
            "point_formats": point_formats,
            "ja3": ja3,
            "ja3_hash": hashlib.md5(ja3.encode()).hexdigest(),
        }
