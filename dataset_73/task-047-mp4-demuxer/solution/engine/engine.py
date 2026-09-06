"""ISO Base Media File Format (MP4) box demuxer.

Walks the box hierarchy, decodes the common movie / track / media-header boxes
and the four sample-table boxes, and is defensive about truncation.
"""
from __future__ import annotations

from engine.boxes import CONTAINER_BOXES, SAMPLE_TABLE_BOXES


class Mp4Engine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def parse(self, mp4_bytes):
        return {"boxes": self._parse_boxes(mp4_bytes, 0, len(mp4_bytes))}

    # -------------------------------------------------------------- walker
    def _parse_boxes(self, blob, start, end):
        boxes = []
        i = start
        while i + 8 <= end:
            size = int.from_bytes(blob[i:i + 4], "big")
            btype = blob[i + 4:i + 8].decode("latin-1")
            header = 8
            if size == 1:
                if i + 16 > end:
                    break
                size = int.from_bytes(blob[i + 8:i + 16], "big")
                header = 16
            elif size == 0:
                size = end - i                     # extends to EOF
            if size < header or i + size > end + 0:
                size = min(size, end - i)
                if size < header:
                    break
            body = blob[i + header:i + size]

            box = {"type": btype, "size": size, "offset": i, "header_size": header}
            if btype in CONTAINER_BOXES:
                box["children"] = self._parse_boxes(blob, i + header, i + size)
            elif btype in SAMPLE_TABLE_BOXES:
                box.update(self._decode_sample_table(btype, body))
            else:
                decoder = getattr(self, f"_decode_{btype}", None)
                if decoder:
                    box.update(decoder(body))
                else:
                    box["data"] = bytes(body)
            boxes.append(box)
            i += size
        return boxes

    # --------------------------------------------------- box field decoders
    @staticmethod
    def _full(body):
        return body[0], int.from_bytes(body[1:4], "big"), body[4:]

    def _decode_ftyp(self, body):
        brands = [body[i:i + 4].decode("latin-1") for i in range(8, len(body) - 3, 4)]
        return {
            "major_brand": body[0:4].decode("latin-1"),
            "minor_version": int.from_bytes(body[4:8], "big"),
            "compatible_brands": brands,
        }

    def _decode_mvhd(self, body):
        version, _flags, rest = self._full(body)
        if version == 1:
            timescale = int.from_bytes(rest[16:20], "big")
            duration = int.from_bytes(rest[20:28], "big")
        else:
            timescale = int.from_bytes(rest[8:12], "big")
            duration = int.from_bytes(rest[12:16], "big")
        return {"version": version, "timescale": timescale, "duration": duration}

    def _decode_tkhd(self, body):
        version, flags, rest = self._full(body)
        if version == 1:
            track_id = int.from_bytes(rest[16:20], "big")
            duration = int.from_bytes(rest[24:32], "big")
        else:
            track_id = int.from_bytes(rest[8:12], "big")
            duration = int.from_bytes(rest[16:20], "big")
        return {"version": version, "flags": flags,
                "track_id": track_id, "duration": duration}

    def _decode_hdlr(self, body):
        _v, _f, rest = self._full(body)
        return {"handler_type": rest[4:8].decode("latin-1")}

    def _decode_sample_table(self, btype, body):
        version, _flags, rest = self._full(body)
        out = {"version": version}
        if btype == "stts":
            n = int.from_bytes(rest[0:4], "big")
            out["entries"] = [
                {"sample_count": int.from_bytes(rest[4 + 8 * k:8 + 8 * k], "big"),
                 "sample_delta": int.from_bytes(rest[8 + 8 * k:12 + 8 * k], "big")}
                for k in range(n)
            ]
        elif btype == "stsc":
            n = int.from_bytes(rest[0:4], "big")
            out["entries"] = [
                {"first_chunk": int.from_bytes(rest[4 + 12 * k:8 + 12 * k], "big"),
                 "samples_per_chunk": int.from_bytes(rest[8 + 12 * k:12 + 12 * k], "big"),
                 "sample_description_index": int.from_bytes(rest[12 + 12 * k:16 + 12 * k], "big")}
                for k in range(n)
            ]
        elif btype == "stsz":
            sample_size = int.from_bytes(rest[0:4], "big")
            count = int.from_bytes(rest[4:8], "big")
            out["sample_size"] = sample_size
            out["sample_count"] = count
            out["entry_sizes"] = (
                [] if sample_size else
                [int.from_bytes(rest[8 + 4 * k:12 + 4 * k], "big") for k in range(count)]
            )
        elif btype == "stco":
            n = int.from_bytes(rest[0:4], "big")
            out["chunk_offsets"] = [
                int.from_bytes(rest[4 + 4 * k:8 + 4 * k], "big") for k in range(n)
            ]
        elif btype == "co64":
            n = int.from_bytes(rest[0:4], "big")
            out["chunk_offsets"] = [
                int.from_bytes(rest[4 + 8 * k:12 + 8 * k], "big") for k in range(n)
            ]
        return out
