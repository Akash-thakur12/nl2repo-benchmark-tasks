"""RFC 8446 TLS 1.3 handshake state machine (client's view of the transcript).

Branches modelled: full 1-RTT server-auth, HelloRetryRequest retry, mutual
(client-certificate) auth, and PSK / 0-RTT resumption. Any out-of-order message
drives the machine to a terminal ERROR state with an ``unexpected_message`` alert.
"""
from __future__ import annotations

import hashlib

from engine.records import (
    MSG_CERTIFICATE, MSG_CERTIFICATE_REQUEST, MSG_CERTIFICATE_VERIFY,
    MSG_CLIENT_HELLO, MSG_ENCRYPTED_EXTENSIONS, MSG_END_OF_EARLY_DATA,
    MSG_FINISHED, MSG_HELLO_RETRY_REQUEST, MSG_KEY_UPDATE, MSG_SERVER_HELLO,
    canonical,
)


class TlsHandshakeEngine:
    STATES = ["START", "WAIT_CH2", "WAIT_SH", "WAIT_EE", "WAIT_CERT_CR",
              "WAIT_CERT", "WAIT_CV", "WAIT_SERVER_FINISHED",
              "WAIT_CLIENT_CERT", "WAIT_CLIENT_CV", "WAIT_CLIENT_FINISHED",
              "CONNECTED", "ERROR"]

    def __init__(self, config=None):
        self.reset()

    def reset(self):
        self.state = "START"
        self._transcript = []
        self._psk_offered = False
        self._early_data_rejected = False
        self._client_auth = False
        self._alert = None

    def configure(self, options):
        self.reset()

    # ------------------------------------------------------------- helpers
    def _as_record(self, msg):
        if isinstance(msg, str):
            return {"type": canonical(msg)}
        rec = dict(msg)
        rec["type"] = canonical(rec.get("type", ""))
        return rec

    def _fail(self, expected):
        self.state = "ERROR"
        self._alert = "unexpected_message"
        return {"ok": False, "state": "ERROR", "alert": "unexpected_message",
                "expected": expected}

    def _ok(self, **extra):
        r = {"ok": True, "state": self.state}
        r.update(extra)
        return r

    # -------------------------------------------------------------- feed
    def feed(self, msg):
        if self.state == "ERROR":
            return {"ok": False, "state": "ERROR", "alert": self._alert}
        rec = self._as_record(msg)
        mtype = rec["type"]
        self._transcript.append(mtype)
        handler = getattr(self, f"_st_{self.state.lower()}")
        return handler(mtype, rec)

    # ---------------------------------------------------------- per-state
    def _st_start(self, m, rec):
        if m == MSG_CLIENT_HELLO:
            self._psk_offered = bool(rec.get("psk"))
            self.state = "WAIT_SH"
            return self._ok(psk=self._psk_offered)
        return self._fail([MSG_CLIENT_HELLO])

    def _st_wait_ch2(self, m, rec):
        if m == MSG_CLIENT_HELLO:
            self.state = "WAIT_SH"
            return self._ok()
        return self._fail([MSG_CLIENT_HELLO])

    def _st_wait_sh(self, m, rec):
        if m == MSG_HELLO_RETRY_REQUEST:
            self.state = "WAIT_CH2"
            return self._ok(retry=True)
        if m == MSG_SERVER_HELLO:
            self.state = "WAIT_EE"
            return self._ok()
        return self._fail([MSG_SERVER_HELLO, MSG_HELLO_RETRY_REQUEST])

    def _st_wait_ee(self, m, rec):
        if m == MSG_ENCRYPTED_EXTENSIONS:
            self._early_data_rejected = bool(rec.get("early_data_rejected"))
            # PSK resumption skips the certificate messages entirely
            self.state = "WAIT_SERVER_FINISHED" if self._psk_offered else "WAIT_CERT_CR"
            return self._ok(early_data_rejected=self._early_data_rejected)
        return self._fail([MSG_ENCRYPTED_EXTENSIONS])

    def _st_wait_cert_cr(self, m, rec):
        if m == MSG_CERTIFICATE_REQUEST:
            self._client_auth = True
            self.state = "WAIT_CERT"
            return self._ok(client_auth=True)
        if m == MSG_CERTIFICATE:
            self.state = "WAIT_CV"
            return self._ok()
        return self._fail([MSG_CERTIFICATE, MSG_CERTIFICATE_REQUEST])

    def _st_wait_cert(self, m, rec):
        if m == MSG_CERTIFICATE:
            self.state = "WAIT_CV"
            return self._ok()
        return self._fail([MSG_CERTIFICATE])

    def _st_wait_cv(self, m, rec):
        if m == MSG_CERTIFICATE_VERIFY:
            self.state = "WAIT_SERVER_FINISHED"
            return self._ok()
        return self._fail([MSG_CERTIFICATE_VERIFY])

    def _st_wait_server_finished(self, m, rec):
        if m == MSG_FINISHED:
            if self._client_auth:
                self.state = "WAIT_CLIENT_CERT"
                return self._ok(need_client_auth=True)
            self.state = "CONNECTED"
            return self._ok()
        return self._fail([MSG_FINISHED])

    def _st_wait_client_cert(self, m, rec):
        if m == MSG_CERTIFICATE:
            self.state = "WAIT_CLIENT_CV"
            return self._ok()
        return self._fail([MSG_CERTIFICATE])

    def _st_wait_client_cv(self, m, rec):
        if m == MSG_CERTIFICATE_VERIFY:
            self.state = "WAIT_CLIENT_FINISHED"
            return self._ok()
        return self._fail([MSG_CERTIFICATE_VERIFY])

    def _st_wait_client_finished(self, m, rec):
        if m == MSG_FINISHED:
            self.state = "CONNECTED"
            return self._ok()
        return self._fail([MSG_FINISHED])

    def _st_connected(self, m, rec):
        if m == MSG_KEY_UPDATE:
            return self._ok(key_update=True)
        if m == MSG_END_OF_EARLY_DATA:
            return self._ok()
        return self._fail([MSG_KEY_UPDATE])

    # ----------------------------------------------------------- queries
    def is_connected(self):
        return self.state == "CONNECTED"

    def can_0rtt(self):
        return self._psk_offered and not self._early_data_rejected

    def key_update(self):
        if self.state != "CONNECTED":
            return False
        self._transcript.append(MSG_KEY_UPDATE)
        return True

    def transcript_hash(self):
        return hashlib.sha256("|".join(self._transcript).encode()).hexdigest()
