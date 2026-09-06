# Standard MIDI File (SMF) Parser

## 1. Overview

Parse an SMF Format 0/1 byte stream. Standard library only; code in `engine/`.
`engine/chunks.py` holds `CHUNK_MTHD` (`b"MThd"`) and `CHUNK_MTRK` (`b"MTrk"`).

## 2. `parse(midi_bytes: bytes) -> dict`

```python
{
  "format": int,
  "tracks": int,
  "division": {"type": "ppq", "ticks_per_quarter": int}
              | {"type": "smpte", "fps": int, "ticks_per_frame": int},
  "track_events": [ [event, ...], ... ],   # one list per MTrk chunk
}
```

The MThd length field is honoured (data starts at `8 + header_length`).

### Events

Every event has `delta` (int, from the VLQ) and `type`.

- **channel** (`0x80..0xEF`): `{"type": "channel", "status", "channel"
  (status & 0x0F), "message", "data"}`. `message` is one of `note_off`,
  `note_on`, `poly_pressure`, `control_change`, `program_change`,
  `channel_pressure`, `pitch_bend`. `program_change` and `channel_pressure`
  carry **one** data byte; the rest carry two. Running status (a data byte where
  a status byte is expected) reuses the previous channel status.
- **meta** (`0xFF`): `{"type": "meta", "meta_type", "meta_name", "data"}` plus
  decoded fields — `set_tempo` -> `tempo_us_per_quarter` + `bpm`;
  `time_signature` -> `numerator`/`denominator`/`clocks_per_click`/
  `notated_32nds`; `key_signature` -> `sharps_flats` (signed) + `minor`;
  text metas -> `text` (latin-1).
- **sysex** (`0xF0` / `0xF7`): `{"type": "sysex", "data"}`.

Raises `ValueError` on a missing `MThd`, a truncated header, a missing / oversized
`MTrk`, a VLQ longer than 4 bytes, running status with no prior status byte, or a
truncated event.

## 3. Example

```python
song = MidiParserEngine().parse(raw_midi_bytes)
song["division"]                          # -> {"type": "ppq", "ticks_per_quarter": 480}
song["track_events"][0][0]["meta_name"]   # -> "end_of_track"
```

## 4. Lifecycle

### `class MidiParserEngine`

- `__init__(self, config=None)` — `config` is accepted and ignored.
- `reset(self)` — re-initialise the engine to a fresh state.
- `configure(self, options)` — accept an `options` dict and call `reset()`.

The engine keeps no state between calls, so `reset()` / `configure()` are effectively no-ops: after either, a subsequent `parse(...)` behaves identically to a freshly constructed engine.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
