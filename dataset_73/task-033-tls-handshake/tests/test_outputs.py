import pytest
from engine.engine import TlsHandshakeEngine

FULL_1RTT = ["ClientHello", "ServerHello", "EncryptedExtensions",
             "Certificate", "CertificateVerify", "Finished"]


@pytest.fixture
def e():
    return TlsHandshakeEngine()


def test_full_handshake_dict_input(e):
    for t in FULL_1RTT:
        assert e.feed({"type": t})["ok"] is True
    assert e.is_connected() is True


def test_full_handshake_string_input(e):
    for m in ["CLIENT_HELLO", "SERVER_HELLO", "ENCRYPTED_EXTENSIONS",
              "CERTIFICATE", "CERTIFICATE_VERIFY", "FINISHED"]:
        assert e.feed(m)["ok"] is True
    assert e.is_connected() is True


def test_out_of_order_message_is_fatal(e):
    r = e.feed("ServerHello")            # before ClientHello
    assert r["ok"] is False and r["state"] == "ERROR"
    assert r["alert"] == "unexpected_message"
    assert "ClientHello" in r["expected"]
    # machine is dead
    assert e.feed("ClientHello")["ok"] is False
    assert e.is_connected() is False


@pytest.mark.parametrize("stop_at", range(1, 6))
def test_incomplete_handshake_not_connected(e, stop_at):
    for t in FULL_1RTT[:stop_at]:
        e.feed({"type": t})
    assert e.is_connected() is False


def test_hello_retry_request_branch(e):
    assert e.feed("ClientHello")["ok"]
    r = e.feed("HelloRetryRequest")
    assert r["ok"] and r.get("retry") is True and e.state == "WAIT_CH2"
    for t in FULL_1RTT:
        assert e.feed({"type": t})["ok"]
    assert e.is_connected()


def test_hrr_requires_second_client_hello(e):
    e.feed("ClientHello")
    e.feed("HelloRetryRequest")
    r = e.feed("ServerHello")            # illegal: need ClientHello again
    assert r["ok"] is False and r["state"] == "ERROR"


def test_mutual_client_auth_branch(e):
    e.feed({"type": "ClientHello"})
    e.feed({"type": "ServerHello"})
    e.feed({"type": "EncryptedExtensions"})
    cr = e.feed({"type": "CertificateRequest"})
    assert cr["ok"] is True and cr["client_auth"] is True
    e.feed({"type": "Certificate"})
    e.feed({"type": "CertificateVerify"})
    fin = e.feed({"type": "Finished"})
    assert fin["ok"] is True and fin["need_client_auth"] is True
    assert e.is_connected() is False
    e.feed({"type": "Certificate"})
    e.feed({"type": "CertificateVerify"})
    assert e.feed({"type": "Finished"})["ok"] is True
    assert e.is_connected() is True


def test_client_auth_not_connected_until_client_finished(e):
    for t in ["ClientHello", "ServerHello", "EncryptedExtensions",
              "CertificateRequest", "Certificate", "CertificateVerify", "Finished"]:
        e.feed({"type": t})
    assert e.is_connected() is False       # still owes its own auth messages


def test_client_hello_response_carries_psk_field(e):
    r = e.feed({"type": "ClientHello", "psk": True})
    assert r["ok"] is True and r["psk"] is True

    e2 = TlsHandshakeEngine()
    r2 = e2.feed({"type": "ClientHello"})
    assert r2["ok"] is True and r2["psk"] is False


def test_psk_resumption_skips_certificates(e):
    e.feed({"type": "ClientHello", "psk": True})
    e.feed({"type": "ServerHello"})
    e.feed({"type": "EncryptedExtensions"})
    assert e.can_0rtt() is True
    assert e.feed({"type": "Finished"})["ok"] is True
    assert e.is_connected() is True


def test_psk_certificate_after_ee_is_illegal(e):
    e.feed({"type": "ClientHello", "psk": True})
    e.feed({"type": "ServerHello"})
    e.feed({"type": "EncryptedExtensions"})
    assert e.feed({"type": "Certificate"})["ok"] is False


def test_0rtt_rejected_by_server(e):
    e.feed({"type": "ClientHello", "psk": True})
    e.feed({"type": "ServerHello"})
    e.feed({"type": "EncryptedExtensions", "early_data_rejected": True})
    assert e.can_0rtt() is False


def test_no_psk_means_no_0rtt(e):
    e.feed("ClientHello")
    assert e.can_0rtt() is False


def test_key_update_only_when_connected(e):
    assert e.key_update() is False
    for t in FULL_1RTT:
        e.feed({"type": t})
    assert e.key_update() is True
    assert e.feed("KeyUpdate")["ok"] is True   # post-handshake KeyUpdate ok


def test_key_update_response_carries_key_update_field(e):
    for t in FULL_1RTT:
        e.feed({"type": t})
    r = e.feed("KeyUpdate")
    assert r["ok"] is True and r["key_update"] is True


def test_transcript_hash_changes_with_messages(e):
    h0 = e.transcript_hash()
    e.feed("ClientHello")
    assert e.transcript_hash() != h0 and len(e.transcript_hash()) == 64


def test_reset_and_configure(e):
    for t in FULL_1RTT:
        e.feed({"type": t})
    e.reset()
    assert e.state == "START" and not e.is_connected()
    e.feed("ClientHello")
    e.configure({})
    assert e.state == "START"
