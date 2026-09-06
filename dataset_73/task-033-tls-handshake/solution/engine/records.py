from __future__ import annotations

MSG_CLIENT_HELLO = "ClientHello"
MSG_HELLO_RETRY_REQUEST = "HelloRetryRequest"
MSG_SERVER_HELLO = "ServerHello"
MSG_ENCRYPTED_EXTENSIONS = "EncryptedExtensions"
MSG_CERTIFICATE_REQUEST = "CertificateRequest"
MSG_CERTIFICATE = "Certificate"
MSG_CERTIFICATE_VERIFY = "CertificateVerify"
MSG_FINISHED = "Finished"
MSG_END_OF_EARLY_DATA = "EndOfEarlyData"
MSG_KEY_UPDATE = "KeyUpdate"

# normalise "SERVER_HELLO" / "server_hello" / "ServerHello" -> canonical
_ALIASES = {
    m.upper(): m for m in [
        MSG_CLIENT_HELLO, MSG_HELLO_RETRY_REQUEST, MSG_SERVER_HELLO,
        MSG_ENCRYPTED_EXTENSIONS, MSG_CERTIFICATE_REQUEST, MSG_CERTIFICATE,
        MSG_CERTIFICATE_VERIFY, MSG_FINISHED, MSG_END_OF_EARLY_DATA,
        MSG_KEY_UPDATE,
    ]
}
_ALIASES["0RTT_DATA"] = MSG_END_OF_EARLY_DATA


def canonical(name: str) -> str:
    key = name.replace(" ", "").replace("_", "").upper()
    for m in _ALIASES.values():
        if m.upper() == key:
            return m
    return _ALIASES.get(name.upper(), name)
