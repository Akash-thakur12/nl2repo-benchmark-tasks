"""Standard MIDI File (SMF) parser.

Handles MThd / MTrk chunks, variable-length delta times, running status,
channel-voice messages (1 or 2 data bytes), meta events (with tempo / time-sig /
key-sig / text decoding) and SysEx.
"""
from __future__ import annotations

from engine.chunks import CHUNK_MTHD, CHUNK_MTRK

_META_NAMES = {
    0x00: "sequence_number", 0x01: "text", 0x02: "copyright",
    0x03: "track_name", 0x04: "instrument_name", 0x05: "lyric",
    0x06: "marker", 0x07: "cue_point", 0x20: "channel_prefix",
    0x2F: "end_of_track", 0x51: "set_tempo", 0x54: "smpte_offset",
    0x58: "time_signature", 0x59: "key_signature", 0x7F: "sequencer_specific",
}
_MSG_NAMES = {
    0x80: "note_off", 0x90: "note_on", 0xA0: "poly_pressure",
    0xB0: "control_change", 0xC0: "program_change", 0xD0: "channel_pressure",
    0xE0: "pitch_bend",
}
_ONE_BYTE = {0xC0, 0xD0}


class MidiParserEngine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _vlq(blob, i):
        value = 0
        for _ in range(4):
            if i >= len(blob):
                raise ValueError("VLQ runs past end of data")
            b = blob[i]
            value = (value << 7) | (b & 0x7F)
            i += 1
            if not b & 0x80:
                return value, i
        raise ValueError("VLQ longer than 4 bytes")

    @staticmethod
    def _decode_division(raw):
        if raw & 0x8000:
            fps = 256 - ((raw >> 8) & 0xFF)
            return {"type": "smpte", "fps": fps, "ticks_per_frame": raw & 0xFF}
        return {"type": "ppq", "ticks_per_quarter": raw}

    # --------------------------------------------------------------- parse
    def parse(self, midi_bytes):
        blob = midi_bytes
        if blob[:4] != CHUNK_MTHD:
            raise ValueError("missing MThd chunk")
        if len(blob) < 14:
            raise ValueError("truncated MThd chunk")
        hlen = int.from_bytes(blob[4:8], "big")
        fmt = int.from_bytes(blob[8:10], "big")
        ntrk = int.from_bytes(blob[10:12], "big")
        division = self._decode_division(int.from_bytes(blob[12:14], "big"))

        out = {
            "format": fmt,
            "tracks": ntrk,
            "division": division,
            "track_events": [],
        }
        i = 8 + hlen
        for _ in range(ntrk):
            if i + 8 > len(blob) or blob[i:i + 4] != CHUNK_MTRK:
                raise ValueError("missing or misplaced MTrk chunk")
            tlen = int.from_bytes(blob[i + 4:i + 8], "big")
            i += 8
            end = i + tlen
            if end > len(blob):
                raise ValueError("MTrk length exceeds file size")
            out["track_events"].append(self._parse_track(blob, i, end))
            i = end
        return out

    def _parse_track(self, blob, i, end):
        events = []
        running_status = None
        while i < end:
            delta, i = self._vlq(blob, i)
            if i >= end:
                raise ValueError("event header truncated")
            status = blob[i]
            if status & 0x80:
                i += 1
            else:
                if running_status is None:
                    raise ValueError("running status with no prior status byte")
                status = running_status

            if status == 0xFF:
                meta_type = blob[i]
                i += 1
                length, i = self._vlq(blob, i)
                data = bytes(blob[i:i + length])
                i += length
                ev = {"delta": delta, "type": "meta", "meta_type": meta_type,
                      "meta_name": _META_NAMES.get(meta_type, f"unknown_{meta_type:#04x}"),
                      "data": data}
                ev.update(self._decode_meta(meta_type, data))
                events.append(ev)
                running_status = None
            elif status in (0xF0, 0xF7):
                length, i = self._vlq(blob, i)
                data = bytes(blob[i:i + length])
                i += length
                events.append({"delta": delta, "type": "sysex", "data": data})
                running_status = None
            elif 0x80 <= status <= 0xEF:
                hi = status & 0xF0
                nbytes = 1 if hi in _ONE_BYTE else 2
                if i + nbytes > end:
                    raise ValueError("channel message data truncated")
                data = [blob[i + k] for k in range(nbytes)]
                i += nbytes
                events.append({
                    "delta": delta, "type": "channel", "status": status,
                    "channel": status & 0x0F, "message": _MSG_NAMES[hi],
                    "data": data,
                })
                running_status = status
            else:
                raise ValueError(f"unexpected status byte {status:#04x}")
        return events

    @staticmethod
    def _decode_meta(meta_type, data):
        if meta_type == 0x51 and len(data) == 3:
            us = int.from_bytes(data, "big")
            return {"tempo_us_per_quarter": us,
                    "bpm": round(60_000_000 / us, 3) if us else None}
        if meta_type == 0x58 and len(data) >= 4:
            return {"numerator": data[0], "denominator": 2 ** data[1],
                    "clocks_per_click": data[2], "notated_32nds": data[3]}
        if meta_type == 0x59 and len(data) == 2:
            sf = data[0] - 256 if data[0] > 127 else data[0]
            return {"sharps_flats": sf, "minor": bool(data[1])}
        if meta_type in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07):
            return {"text": data.decode("latin-1")}
        return {}
