from __future__ import annotations

# Wire constants for the record layer and the handshake protocol.
# Field 1 of the fingerprint is the client_version carried inside the handshake
# body; the record header's version is a transport artefact (see
# docs/ja3-v2-field-notes.md).
TLS_HANDSHAKE_CLIENT_HELLO = 0x01
TLS_RECORD_HANDSHAKE = 0x16
