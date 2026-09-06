import pytest
from engine.engine import CsrfMiddlewareEngine, ValidationError, UnauthorizedError


def make():
    return CsrfMiddlewareEngine({"secret": b"k", "allowed_origins": ["https://example.com"]})


def test_issue_and_verify_double_submit():
    e = make()
    t = e.issue("sess1")
    ok = e.verify(
        {"X-CSRF-Token": t, "Origin": "https://example.com/dashboard"},
        {"csrf_token": t},
        "POST",
        session_id="sess1",
    )
    assert ok is True


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "get", "Head"])
def test_safe_methods_exempt(method):
    assert make().verify({}, {}, method) is True


def test_missing_header_or_cookie_is_validation_error():
    e = make()
    t = e.issue("s")
    with pytest.raises(ValidationError):
        e.verify({}, {"csrf_token": t}, "POST")
    with pytest.raises(ValidationError):
        e.verify({"X-CSRF-Token": t}, {}, "POST")


def test_double_submit_mismatch_rejected():
    e = make()
    t = e.issue("s")
    with pytest.raises(UnauthorizedError):
        e.verify({"X-CSRF-Token": t}, {"csrf_token": t[:-1] + ("0" if t[-1] != "0" else "1")}, "POST")


def test_malformed_token_is_validation_error():
    e = make()
    with pytest.raises(ValidationError):
        e.verify({"X-CSRF-Token": "no-dot-here"}, {"csrf_token": "no-dot-here"}, "POST")


def test_bad_signature_rejected():
    e = make()
    t = e.issue("s")
    nonce = t.split(".")[0]
    forged = f"{nonce}." + "0" * 64
    with pytest.raises(UnauthorizedError):
        e.verify({"X-CSRF-Token": forged}, {"csrf_token": forged}, "POST", session_id="s")


def test_signature_not_checked_without_session_id():
    e = make()
    t = e.issue("s")
    nonce = t.split(".")[0]
    forged = f"{nonce}." + "0" * 64
    # no session_id -> integrity of the signature is not asserted, only double-submit
    assert e.verify({"X-CSRF-Token": forged}, {"csrf_token": forged}, "POST") is True


def test_origin_allowlist():
    e = make()
    t = e.issue("s")
    with pytest.raises(UnauthorizedError):
        e.verify({"X-CSRF-Token": t, "Origin": "https://evil.com"},
                 {"csrf_token": t}, "POST", session_id="s")


def test_referer_used_when_no_origin():
    e = make()
    t = e.issue("s")
    assert e.verify({"X-CSRF-Token": t, "Referer": "https://example.com/page"},
                    {"csrf_token": t}, "POST", session_id="s") is True
    with pytest.raises(UnauthorizedError):
        e.verify({"X-CSRF-Token": t, "Referer": "https://evil.com/x"},
                 {"csrf_token": t}, "POST", session_id="s")


def test_header_lookup_is_case_insensitive():
    e = make()
    t = e.issue("s")
    assert e.verify({"x-csrf-token": t, "origin": "https://example.com"},
                    {"csrf_token": t}, "POST", session_id="s") is True


def test_no_allowlist_skips_origin_check():
    e = CsrfMiddlewareEngine({"secret": b"k"})   # no allowed_origins
    t = e.issue("s")
    assert e.verify({"X-CSRF-Token": t, "Origin": "https://anywhere.example"},
                    {"csrf_token": t}, "POST", session_id="s") is True


def test_configure_updates_secret_and_allowlist():
    e = make()
    t = e.issue("s")
    e.configure({"secret": b"rotated", "allowed_origins": ["https://new.example"]})
    with pytest.raises(UnauthorizedError):     # old token no longer verifies
        e.verify({"X-CSRF-Token": t}, {"csrf_token": t}, "POST", session_id="s")
    t2 = e.issue("s")
    assert e.verify({"X-CSRF-Token": t2, "Origin": "https://new.example"},
                    {"csrf_token": t2}, "POST", session_id="s") is True


def test_reset_is_a_noop():
    e = make()
    t = e.issue("s")
    e.reset()
    assert e.verify({"X-CSRF-Token": t, "Origin": "https://example.com"},
                    {"csrf_token": t}, "POST", session_id="s") is True
