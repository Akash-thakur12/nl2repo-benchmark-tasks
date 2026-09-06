"""DICOM Part 10 dataset parser.

Handles the 128-byte preamble + 'DICM', explicit-VR little-endian and
implicit-VR little-endian encodings, the 2-byte vs 12-byte element-header split,
common VR value decoding, and nested sequences (SQ) including undefined length.
"""
from __future__ import annotations

from engine.tags import IMPLICIT_VR, TAG_NAMES

_LONG_VRS = {"OB", "OW", "OF", "OD", "OL", "SQ", "UN", "UT", "UC", "UR"}
_STR_VRS = {"AE", "AS", "CS", "DA", "DS", "DT", "IS", "LO", "LT", "PN",
            "SH", "ST", "TM", "UI", "UC", "UR", "UT"}
_ITEM = (0xFFFE, 0xE000)
_ITEM_DELIM = (0xFFFE, 0xE00D)
_SEQ_DELIM = (0xFFFE, 0xE0DD)
_UNDEFINED = 0xFFFFFFFF


class DicomEngine:
    TAG_NAMES = TAG_NAMES

    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def parse(self, dicom_bytes, implicit_vr=False):
        blob = dicom_bytes
        if len(blob) < 132 or blob[128:132] != b"DICM":
            raise ValueError("missing DICM preamble")
        elements, _ = self._parse_dataset(blob, 132, len(blob), implicit_vr)
        return elements

    # ---------------------------------------------------------- dataset
    def _parse_dataset(self, blob, i, end, implicit_vr):
        out = {}
        while i + 8 <= end:
            group = int.from_bytes(blob[i:i + 2], "little")
            element = int.from_bytes(blob[i + 2:i + 4], "little")
            tag = (group, element)

            if tag in (_ITEM_DELIM, _SEQ_DELIM):
                i += 8
                return out, i

            if implicit_vr:
                vr = IMPLICIT_VR.get(tag, "UN")
                length = int.from_bytes(blob[i + 4:i + 8], "little")
                header_end = i + 8
            else:
                vr = blob[i + 4:i + 6].decode("ascii", "replace")
                if vr in _LONG_VRS:
                    length = int.from_bytes(blob[i + 8:i + 12], "little")
                    header_end = i + 12
                else:
                    length = int.from_bytes(blob[i + 6:i + 8], "little")
                    header_end = i + 8

            name = TAG_NAMES.get(tag, f"({group:04x},{element:04x})")

            if vr == "SQ":
                items, i = self._parse_sequence(blob, header_end, end, length,
                                                implicit_vr)
                out[name] = {"vr": "SQ", "value": items,
                             "group": group, "element": element}
                continue

            if length == _UNDEFINED:
                raise ValueError("undefined length outside a sequence")
            value_bytes = blob[header_end:header_end + length]
            if len(value_bytes) < length:
                raise ValueError("element value truncated")
            i = header_end + length
            out[name] = {
                "vr": vr,
                "value": self._decode(vr, bytes(value_bytes)),
                "group": group,
                "element": element,
            }
        return out, i

    def _parse_sequence(self, blob, i, end, seq_length, implicit_vr):
        items = []
        stop = end if seq_length == _UNDEFINED else i + seq_length
        while i + 8 <= stop:
            group = int.from_bytes(blob[i:i + 2], "little")
            element = int.from_bytes(blob[i + 2:i + 4], "little")
            item_len = int.from_bytes(blob[i + 4:i + 8], "little")
            i += 8
            if (group, element) == _SEQ_DELIM:
                break
            if (group, element) != _ITEM:
                raise ValueError("expected an item tag inside a sequence")
            item_stop = end if item_len == _UNDEFINED else i + item_len
            item, i = self._parse_dataset(blob, i, item_stop, implicit_vr)
            items.append(item)
            if item_len == _UNDEFINED:
                continue
        return items, i

    # ----------------------------------------------------------- decode
    @staticmethod
    def _decode(vr, raw):
        if vr in _STR_VRS:
            return raw.decode("latin-1").rstrip(" \x00")
        if vr == "US":
            return int.from_bytes(raw[:2], "little") if len(raw) >= 2 else 0
        if vr == "UL":
            return int.from_bytes(raw[:4], "little") if len(raw) >= 4 else 0
        if vr == "SS":
            v = int.from_bytes(raw[:2], "little")
            return v - 65536 if v & 0x8000 else v
        return raw
