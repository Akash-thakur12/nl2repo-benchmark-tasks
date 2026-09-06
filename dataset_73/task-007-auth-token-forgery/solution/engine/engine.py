"""Offline audit engine for `tokend` truncated-HMAC request tags.

Two modes share one class:

* *legacy mode* -- no ``keyring`` in the config. The tag width is the fixed
  ``config["trunc"]`` and there is no notion of a key id or a capture epoch.
  This is the pre-4417 oracle and its behaviour is unchanged.
* *keyring mode* -- a KMS export is supplied. Every tag width is then the width
  that was in force at the instant of the event being audited, resolved from
  the key's ``width_history``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os

#: The tag field on the wire is a fixed-width protocol field.
FRAME_OCTETS = 8


def _as_bytes(value):
    return value.encode() if isinstance(value, str) else value


def _load_keyring(source):
    """Accept a parsed export, a path to one, or ``None``."""
    if source is None:
        return None
    if isinstance(source, dict):
        return source
    if isinstance(source, (str, bytes, os.PathLike)):
        with open(source, "r", encoding="utf-8") as handle:
            return json.load(handle)
    raise TypeError("keyring must be a dict, a path, or None")


def _index_keyring(export):
    """kid -> {secret, mac_bytes, history}, history sorted by ``from``.

    ``width_history`` is an append-only operator log, so its file order is the
    order rows were *written*, not the order the changes took effect: a
    backfilled row can sit after a later one. Sorting by ``from`` is what makes
    the resolution independent of that.
    """
    index = {}
    if not export:
        return index
    for row in export.get("keys", []):
        history = sorted(
            (
                (int(entry["from"]), int(entry["mac_bytes"]))
                for entry in row.get("width_history", [])
            ),
            key=lambda pair: pair[0],
        )
        index[row["kid"]] = {
            "secret": bytes.fromhex(row["secret_hex"]),
            "mac_bytes": row.get("mac_bytes"),
            "history": history,
        }
    return index


class AuthTokenEngine:
    """Truncated HMAC-SHA256 tag oracle, capture replay, and key recovery."""

    def __init__(self, config=None):
        self._samples = []
        self._apply(config or {}, fresh=True)

    # ------------------------------------------------------------------ setup
    def _apply(self, config, fresh=False):
        if fresh:
            key = config.get("key", b"k" * 8)
            self._key = _as_bytes(key)
            self._trunc = config.get("trunc", 8)
            self._keyring = _load_keyring(config.get("keyring"))
            self._kid = config.get("kid")
            self._clock = config.get("clock")
        else:
            if "key" in config:
                self._key = _as_bytes(config["key"])
            if "trunc" in config:
                self._trunc = config["trunc"]
            if "keyring" in config:
                self._keyring = _load_keyring(config["keyring"])
            if "kid" in config:
                self._kid = config["kid"]
            if "clock" in config:
                self._clock = config["clock"]
        self._index = _index_keyring(self._keyring)

    def reset(self):
        """Return the engine to the no-samples state."""
        self._samples = []

    def configure(self, options):
        """Merge new options and clear all recorded samples."""
        self._apply(options or {})
        self._samples = []

    # ------------------------------------------------------- width resolution
    def tag_width_at(self, kid, ts):
        """Octets of MAC in force for ``kid`` at epoch second ``ts``.

        The entry that governs an instant is the latest one whose ``from`` is
        at or before it; ``from`` is inclusive, so a capture taken at exactly
        the changeover second already uses the new width. Before the first
        entry no width was in force and there is nothing to resolve, which is
        not the same as "the default". The row's top-level ``mac_bytes`` is
        what the console renders as of the export date; it is not the width of
        any earlier event.
        """
        row = self._index.get(kid)
        if row is None or ts is None:
            return None
        width = None
        for start, mac_bytes in row["history"]:      # sorted by `from`
            if start <= ts:
                width = mac_bytes
            else:
                break
        return width

    def _secret(self, kid):
        row = self._index.get(kid)
        return None if row is None else row["secret"]

    # ------------------------------------------------------------ tag oracle
    def _now(self):
        if self._clock is not None:
            return self._clock()
        if self._keyring is not None:
            return self._keyring.get("generated_at")
        return None

    def sign(self, msg):
        """The tag tokend stamps for ``msg``.

        Legacy mode truncates to ``config["trunc"]``. Keyring mode truncates to
        the width in force for ``config["kid"]`` at the configured clock's
        instant, and raises ``ValueError`` when no width was in force then.
        """
        if self._keyring is not None and self._kid is not None:
            secret = self._secret(self._kid)
            if secret is None:
                raise ValueError("kid %r is not in the keyring" % (self._kid,))
            width = self.tag_width_at(self._kid, self._now())
            if width is None:
                raise ValueError("no tag width in force for %r at that instant"
                                 % (self._kid,))
            return hmac.new(secret, msg, hashlib.sha256).digest()[:width]
        return hmac.new(self._key, msg, hashlib.sha256).digest()[: self._trunc]

    def verify(self, msg, token):
        """True when ``token`` carries tokend's tag for ``msg``.

        In keyring mode ``token`` may be the bare tag or the full
        ``FRAME_OCTETS``-octet wire field, in which case the pad region beyond
        the tag must be zero.
        """
        expected = self.sign(msg)
        if self._keyring is not None and self._kid is not None:
            width = len(expected)
            if len(token) == width:
                return hmac.compare_digest(expected, token)
            if len(token) == FRAME_OCTETS:
                if any(token[width:]):
                    return False
                return hmac.compare_digest(expected, token[:width])
            return False
        return hmac.compare_digest(expected, token[: self._trunc])

    # ---------------------------------------------------------- capture audit
    @staticmethod
    def _message(record):
        if "msg_b64" in record:
            return base64.b64decode(record["msg_b64"])
        if "msg_hex" in record:
            return bytes.fromhex(record["msg_hex"])
        return _as_bytes(record["msg"])

    @staticmethod
    def _frame(tag_hex):
        """The wire field as bytes, or None when it is not a valid field."""
        try:
            raw = bytes.fromhex(tag_hex)
        except (ValueError, TypeError, binascii.Error):
            return None
        return raw if len(raw) == FRAME_OCTETS else None

    def audit(self, record):
        """Replay one collector capture line and return tokend's verdict.

        One of ``ok``, ``bad-tag``, ``malformed``, ``unknown-kid``,
        ``no-epoch``.
        """
        if self._keyring is None:
            raise ValueError("audit requires a keyring")
        kid = record.get("kid")
        secret = self._secret(kid)
        if secret is None:
            return "unknown-kid"
        width = self.tag_width_at(kid, record.get("captured_at"))
        if width is None:
            return "no-epoch"
        frame = self._frame(record.get("tag_hex"))
        if frame is None or any(frame[width:]):
            return "malformed"
        expected = hmac.new(secret, self._message(record),
                            hashlib.sha256).digest()[:width]
        return "ok" if hmac.compare_digest(expected, frame[:width]) else "bad-tag"

    def audit_all(self, records):
        """``audit`` over an iterable of capture lines."""
        return [self.audit(record) for record in records]

    # ------------------------------------------------------------- recovery
    def add_sample(self, msg, token_hex, meta=None):
        """Record an observed (message, tag field) pair.

        ``meta`` may carry ``kid`` and ``captured_at``; with a keyring
        configured that is what lets the sample be checked at its own epoch
        width.
        """
        self._samples.append((msg, token_hex, dict(meta or {})))

    def _evidence(self):
        """(message, expected tag, width) for every *usable* sample.

        A sample whose width cannot be resolved -- unknown kid, an instant
        before the key's first width entry, or a frame that is not a valid
        wire field -- carries no information and is dropped. It is not counted
        as a mismatch.
        """
        out = []
        for msg, token_hex, meta in self._samples:
            if self._keyring is not None and meta.get("kid") is not None:
                kid = meta["kid"]
                if self._secret(kid) is None:
                    continue
                width = self.tag_width_at(kid, meta.get("captured_at"))
                if width is None:
                    continue
                frame = self._frame(token_hex)
                if frame is None or any(frame[width:]):
                    continue
                out.append((msg, frame[:width], width))
            else:
                try:
                    tag = bytes.fromhex(token_hex)
                except (ValueError, TypeError, binascii.Error):
                    continue
                out.append((msg, tag, self._trunc))
        return out

    def matching_keys(self, candidates):
        """Every candidate reproducing all usable samples, in candidate order.

        Duplicates are kept: the list is the search result, not the verdict.
        """
        evidence = self._evidence()
        if not evidence:
            return []
        found = []
        for candidate in candidates:
            key = _as_bytes(candidate)
            if all(
                hmac.new(key, msg, hashlib.sha256).digest()[:width] == tag
                for msg, tag, width in evidence
            ):
                found.append(candidate)
        return found

    def recover_key(self, candidates):
        """The key that signed the recorded samples, or None.

        Truncation makes this search non-injective, so a match is only an
        identification when the matched candidates are all the same key
        material. Distinct materials that all fit the evidence are a
        non-answer; the same material listed twice (or spelled once as ``str``
        and once as ``bytes``) is still one answer.
        """
        matches = self.matching_keys(candidates)
        if not matches:
            return None
        materials = {_as_bytes(match) for match in matches}
        if len(materials) != 1:
            return None
        return materials.pop()
