from __future__ import annotations

import struct

U16_MAX = 0xFFFF
U32_MAX = 0xFFFFFFFF

#: Highest representable magnitude of a u16 field: 0xFFFF is spent as a
#: sentinel in every unsigned width, so it can never be read as a count.
U16_LIMIT = 0xFFFE

#: Vendored copy of registry/tags.csv (tag, from_rev, encoding).  The codec
#: must not touch the filesystem at run time, so the table lives in code.
REGISTRY_ROWS = (
    (0x14, 1, "delta"),
    (0x15, 1, "absolute"),
    (0x20, 1, "absolute"),
    (0x22, 1, "absolute"),
    (0x22, 7, "delta"),
    (0x30, 9, "delta"),
)

#: Newest revision present in the registry; the default when a blob carries no
#: in-band marker and the caller passed no explicit revision.
REGISTRY_LATEST = max(row[1] for row in REGISTRY_ROWS)

TAG_REVISION_MARKER = 0x0E
TAG_STREAM_TERMINATOR = 0x0F


def _zigzag_encode(delta):
    """Map a signed 32-bit delta onto an unsigned u32 (protobuf sint32)."""
    return ((delta << 1) ^ (delta >> 31)) & U32_MAX


def _zigzag_decode(field):
    """Inverse of :func:`_zigzag_encode`."""
    return (field >> 1) ^ -(field & 1)


def _to_signed32(unsigned):
    return unsigned - (1 << 32) if unsigned >= (1 << 31) else unsigned


class CustomBinaryEngine:
    """Encode/decode the BIN1 compact record stream."""

    MAGIC = b"BIN1"

    def __init__(self, config=None):
        self._constructed = dict(config or {})
        self._options = dict(self._constructed)

    # -- configuration -------------------------------------------------

    def reset(self):
        """Restore the options the engine was constructed with."""
        self._options = dict(self._constructed)

    def configure(self, options):
        """Merge caller options over the current ones."""
        if options:
            self._options.update(options)

    @property
    def _default_revision(self):
        rev = self._options.get("registry_revision")
        if rev is None:
            return REGISTRY_LATEST
        return int(rev)

    # -- registry ------------------------------------------------------

    @staticmethod
    def encoding_for(tag, revision):
        """Encoding in force for ``tag`` at registry ``revision``.

        The row that applies is the one with the greatest ``from_rev`` that is
        not newer than ``revision``.  A tag with no applicable row -- including
        every tag in the reserved 0x00..0x0F transport range -- is absolute.
        """
        best_rev = None
        best = "absolute"
        for row_tag, from_rev, encoding in REGISTRY_ROWS:
            if row_tag != tag or from_rev > revision:
                continue
            if best_rev is None or from_rev > best_rev:
                best_rev = from_rev
                best = encoding
        return best

    # -- encode --------------------------------------------------------

    def encode(self, recs):
        recs = list(recs)
        if len(recs) > U16_LIMIT:
            raise ValueError(
                "record count %d is not representable: 0xFFFF is reserved"
                % len(recs))

        out = bytearray()
        out += self.MAGIC
        out += struct.pack("<H", len(recs))

        first_index = {}          # name bytes -> index of first record using it
        previous = {}             # (tag, name bytes) -> previous logical value
        revision = self._default_revision

        for index, rec in enumerate(recs):
            tag = rec["tag"]
            value = rec["value"]
            name_bytes = rec["name"].encode("utf-8")

            if not isinstance(tag, int) or isinstance(tag, bool):
                raise ValueError("tag must be an int")
            if not 0 <= tag <= 0xFF:
                raise ValueError("tag out of u8 range: %r" % (tag,))
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("value must be an int")
            if not 0 <= value <= U32_MAX:
                raise ValueError("value out of u32 range: %r" % (value,))
            if len(name_bytes) > U16_LIMIT:
                raise ValueError(
                    "name of %d UTF-8 bytes is not representable: 0xFFFF is "
                    "reserved" % len(name_bytes))

            out += struct.pack("<B", tag)
            if name_bytes in first_index:
                out += struct.pack("<H", U16_MAX)
                out += struct.pack("<H", first_index[name_bytes])
            else:
                first_index[name_bytes] = index
                out += struct.pack("<H", len(name_bytes))
                out += name_bytes

            key = (tag, name_bytes)
            if self.encoding_for(tag, revision) == "delta" and key in previous:
                delta = _to_signed32((value - previous[key]) & U32_MAX)
                field = _zigzag_encode(delta)
            else:
                field = value
            previous[key] = value
            out += struct.pack("<I", field)

            if tag == TAG_REVISION_MARKER:
                revision = value

        return bytes(out)

    # -- decode --------------------------------------------------------

    def decode(self, blob):
        blob = bytes(blob)
        if blob[:4] != self.MAGIC:
            raise ValueError("bad magic")
        if len(blob) < 6:
            raise ValueError("truncated header")
        count = struct.unpack("<H", blob[4:6])[0]
        streamed = count == U16_MAX

        out = []
        names = []                # resolved name bytes, by record index
        previous = {}
        revision = self._default_revision
        offset = 6
        index = 0

        while streamed or index < count:
            if offset + 3 > len(blob):
                raise ValueError("truncated record header")
            tag = blob[offset]
            offset += 1
            name_len = struct.unpack("<H", blob[offset:offset + 2])[0]
            offset += 2

            if name_len == U16_MAX:
                if offset + 2 > len(blob):
                    raise ValueError("truncated name back-reference")
                ref = struct.unpack("<H", blob[offset:offset + 2])[0]
                offset += 2
                if ref >= index:
                    raise ValueError(
                        "dangling name back-reference %d at record %d"
                        % (ref, index))
                name_bytes = names[ref]
            else:
                if offset + name_len > len(blob):
                    raise ValueError("truncated record body")
                name_bytes = blob[offset:offset + name_len]
                offset += name_len

            if offset + 4 > len(blob):
                raise ValueError("truncated record body")
            field = struct.unpack("<I", blob[offset:offset + 4])[0]
            offset += 4

            if (streamed and tag == TAG_STREAM_TERMINATOR
                    and name_len == 0 and field == U32_MAX):
                return out

            names.append(name_bytes)
            key = (tag, name_bytes)
            if self.encoding_for(tag, revision) == "delta" and key in previous:
                value = (previous[key] + _zigzag_decode(field)) & U32_MAX
            else:
                value = field
            previous[key] = value

            out.append({
                "tag": tag,
                "name": name_bytes.decode("utf-8"),
                "value": value,
            })
            if tag == TAG_REVISION_MARKER:
                revision = value
            index += 1

        return out
