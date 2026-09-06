import base64
import hashlib
import hmac
import json

import pytest
from engine.engine import JwtKeyConfusionEngine, UnauthorizedError, ValidationError
from engine.verifier import detect_key_confusion


def seg(obj):
    return base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def raw_seg(text):
    """base64url a header/payload written out by hand, duplicates and all."""
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


def std_seg(obj):
    """The STANDARD-alphabet (not urlsafe) encoding of a JSON object."""
    return base64.b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()


def engine():
    return JwtKeyConfusionEngine({"hmac_key": b"k", "rsa_pub": b"PUB"})


# --------------------------------------------------------------------------
# Pre-existing coverage
# --------------------------------------------------------------------------

def test_accepts_pinned_rs256():
    e = JwtKeyConfusionEngine({"hmac_key": b"k", "rsa_pub": b"PUB"})
    h, p, s = seg({"alg": "RS256", "typ": "JWT"}), seg({"sub": "x"}), b64(b"PUB")
    assert e.verify(f"{h}.{p}.{s}")["sub"] == "x"


@pytest.mark.parametrize("alg", ["HS256", "HS384", "none", "None", "ES256", ""])
def test_rejects_any_alg_that_is_not_the_pin(alg):
    e = JwtKeyConfusionEngine({"hmac_key": b"k", "rsa_pub": b"PUB"})
    h, p = seg({"alg": alg, "typ": "JWT"}), seg({"sub": "x"})
    with pytest.raises(UnauthorizedError):
        e.verify(f"{h}.{p}.{b64(b'whatever')}")


@pytest.mark.parametrize("token", ["", "one", "one.two", "one.two.three.four"])
def test_malformed_token_raises_validation_error(token):
    e = JwtKeyConfusionEngine()
    with pytest.raises(ValidationError):
        e.verify(token)


def test_unparseable_header_raises_validation_error():
    e = JwtKeyConfusionEngine()
    with pytest.raises(ValidationError):
        e.verify("!!!.@@@.###")


def test_reset_restores_rs256_pin():
    e = JwtKeyConfusionEngine({"hmac_key": b"k", "rsa_pub": b"PUB"})
    e.configure({"alg": "HS256"})
    e.reset()
    h, p = seg({"alg": "HS256"}), seg({"sub": "x"})
    with pytest.raises(UnauthorizedError):
        e.verify(f"{h}.{p}.{b64(b'x')}")


def test_configure_to_hs256_detects_confused_key():
    e = JwtKeyConfusionEngine({"hmac_key": b"k", "rsa_pub": b"PUB"})
    e.configure({"alg": "HS256"})
    h, p = seg({"alg": "HS256"}), seg({"sub": "x"})
    forged = b64(hmac.new(b"PUB", f"{h}.{p}".encode(), hashlib.sha256).digest())
    assert e.verify(f"{h}.{p}.{forged}")["sub"] == "x"     # HMAC over the RSA pubkey
    with pytest.raises(UnauthorizedError):
        e.verify(f"{h}.{p}.{b64(b'not the right mac')}")


def test_detect_key_confusion_helper():
    assert detect_key_confusion("HS256", "RSA public key") is True
    assert detect_key_confusion("HS256", "rsa") is True
    assert detect_key_confusion("RS256", "RSA") is False
    assert detect_key_confusion("HS256", "oct secret") is False
    assert JwtKeyConfusionEngine.detects_confusion("HS256", "RSA") is True


# --------------------------------------------------------------------------
# Segment encoding (environment/docs/segment-encoding.md)
# --------------------------------------------------------------------------

def test_rejects_standard_alphabet_plus_in_header():
    """A header segment carrying '+' is not base64url, even though a lax
    decoder yields a perfectly valid RS256 header from it."""
    e = engine()
    h = std_seg({"alg": "RS256", "kid": "a~"})
    assert "+" in h
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_rejects_standard_alphabet_slash_in_header():
    """A header segment carrying '/' is not base64url."""
    e = engine()
    h = std_seg({"alg": "RS256", "kid": "a?b>c"})
    assert "/" in h
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


@pytest.mark.parametrize("position", [0, 1, 2])
def test_rejects_non_alphabet_char_in_any_segment(position):
    """The alphabet check applies to all three segments, signature included."""
    e = engine()
    parts = [seg({"alg": "RS256"}), seg({"sub": "x"}), b64(b"sig")]
    parts[position] = parts[position][:4] + "*" + parts[position][4:]
    with pytest.raises(ValidationError):
        e.verify(".".join(parts))


@pytest.mark.parametrize("suffix", ["=", "==", "\n", "\t", " "])
def test_rejects_trailing_padding_and_whitespace(suffix):
    """Segments are unpadded and byte-exact: no padding, no stripping."""
    e = engine()
    h = seg({"alg": "RS256"}) + suffix
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_rejects_segment_whose_length_is_one_mod_four():
    """No base64 encoding has a length congruent to 1 modulo 4."""
    e = engine()
    h = seg({"alg": "RS256"})
    h = h + "A" * ((1 - len(h)) % 4)
    assert len(h) % 4 == 1
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_accepts_hyphen_and_underscore_segments():
    """'-' and '_' are legal base64url; the rule must not over-reject them."""
    e = engine()
    h = seg({"alg": "RS256", "kid": "a~b?c~d?"})
    assert "-" in h and "_" in h
    s = b64(b"\xfb\xff\xbe\xfa")
    assert "-" in s or "_" in s
    assert e.verify(f"{h}.{seg({'sub': 'x'})}.{s}")["sub"] == "x"


# --------------------------------------------------------------------------
# JSON structure (environment/docs/token-structure.md)
# --------------------------------------------------------------------------

def test_duplicate_header_member_rejected_when_last_wins_matches_pin():
    """{"alg":"none","alg":"RS256"} is a parser differential, not an RS256 token."""
    e = engine()
    h = raw_seg('{"alg":"none","alg":"RS256"}')
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_duplicate_header_member_rejected_in_either_order():
    """The disposition does not depend on which duplicate comes first."""
    e = engine()
    h = raw_seg('{"alg":"RS256","alg":"HS256"}')
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_duplicate_non_alg_header_member_rejected():
    """Any repeated member name is structural, not only 'alg'."""
    e = engine()
    h = raw_seg('{"alg":"RS256","kid":"a","kid":"bb"}')
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_duplicate_payload_member_rejected():
    """Duplicate member names in the payload object are rejected too."""
    e = engine()
    p = raw_seg('{"sub":"a","sub":"b"}')
    with pytest.raises(ValidationError):
        e.verify(f"{seg({'alg': 'RS256'})}.{p}.{b64(b'sig')}")


def test_duplicate_member_in_nested_object_rejected():
    """Nesting does not exempt an object from the duplicate rule."""
    e = engine()
    h = raw_seg('{"alg":"RS256","cnf":{"kid":"a","kid":"b"}}')
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_duplicate_member_inside_array_element_rejected():
    """'Any nesting depth' includes objects that sit inside a JSON array."""
    e = engine()
    p = raw_seg('{"sub":"x","aud":[{"id":"a","id":"b"}]}')
    with pytest.raises(ValidationError):
        e.verify(f"{seg({'alg': 'RS256'})}.{p}.{b64(b'sig')}")


def test_duplicate_detection_precedes_alg_check():
    """Structurally defective AND off-pin resolves to ValidationError."""
    e = engine()
    h = raw_seg('{"alg":"HS256","alg":"HS256"}')
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_malformed_segment_precedes_alg_check():
    """Encoding is validated before authorization, so this is not a downgrade."""
    e = engine()
    h = "eyJhbGci*OiJIUzI1NiJ9"          # decodes laxly to {"alg":"HS256"}
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_non_object_header_rejected():
    """A header that decodes to JSON but not to an object is malformed."""
    e = engine()
    h = raw_seg('["RS256"]')
    with pytest.raises(ValidationError):
        e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


def test_alg_comparison_is_case_sensitive():
    """RFC 7515 alg values are case-sensitive; 'rs256' is not the RS256 pin."""
    e = engine()
    for variant in ("rs256", "Rs256", "RS256 "):
        h = seg({"alg": variant})
        with pytest.raises(UnauthorizedError):
            e.verify(f"{h}.{seg({'sub': 'x'})}.{b64(b'sig')}")


# --------------------------------------------------------------------------
# The algorithm register (environment/docs/alg-register.md)
# --------------------------------------------------------------------------

def test_configure_none_leaves_pin_unchanged():
    """'none' has no register row, so pinning it is refused outright."""
    e = engine()
    e.configure({"alg": "none"})
    h, p = seg({"alg": "none"}), seg({"sub": "x"})
    with pytest.raises(UnauthorizedError):
        e.verify(f"{h}.{p}.{b64(b'sig')}")
    ok = f"{seg({'alg': 'RS256'})}.{p}.{b64(b'sig')}"
    assert e.verify(ok)["sub"] == "x"


def test_configure_future_dated_es256_leaves_pin_unchanged():
    """ES256's only row is 'permitted' but takes effect after the snapshot.

    Reading the register as "the last row for this alg wins" without comparing
    the effective date to the 2026-09-01 snapshot makes ES256 look pinnable.
    """
    e = engine()
    e.configure({"alg": "ES256"})
    p = seg({"sub": "x"})
    with pytest.raises(UnauthorizedError):
        e.verify(f"{seg({'alg': 'ES256'})}.{p}.{b64(b'sig')}")
    assert e.verify(f"{seg({'alg': 'RS256'})}.{p}.{b64(b'sig')}")["sub"] == "x"


def test_configure_revoked_hs384_leaves_pin_unchanged():
    """HS384 was permitted in 2023 and revoked in 2025; the later row wins."""
    e = engine()
    e.configure({"alg": "HS384"})
    p = seg({"sub": "x"})
    with pytest.raises(UnauthorizedError):
        e.verify(f"{seg({'alg': 'HS384'})}.{p}.{b64(b'sig')}")
    assert e.verify(f"{seg({'alg': 'RS256'})}.{p}.{b64(b'sig')}")["sub"] == "x"


def test_configure_proposed_only_es512_leaves_pin_unchanged():
    """ES512's row is dated before the snapshot but its status is 'proposed'."""
    e = engine()
    e.configure({"alg": "ES512"})
    p = seg({"sub": "x"})
    with pytest.raises(UnauthorizedError):
        e.verify(f"{seg({'alg': 'ES512'})}.{p}.{b64(b'sig')}")
    assert e.verify(f"{seg({'alg': 'RS256'})}.{p}.{b64(b'sig')}")["sub"] == "x"


def test_configure_rs384_revocation_is_not_yet_in_force():
    """RS384 was permitted in 2022; its 'revoked' row is dated 2026-12-01, i.e.
    after the snapshot, so the withdrawal has not taken effect and the pin
    request is still honoured. The mirror image of the ES256 case."""
    e = engine()
    e.configure({"alg": "RS384"})
    p = seg({"sub": "x"})
    assert e.verify(f"{seg({'alg': 'RS384'})}.{p}.{b64(b'sig')}")["sub"] == "x"
    with pytest.raises(UnauthorizedError):
        e.verify(f"{seg({'alg': 'RS256'})}.{p}.{b64(b'sig')}")


def test_configure_permitted_ps256_takes_effect():
    """PS256 was proposed in 2023 and permitted in 2024, so it is pinnable."""
    e = engine()
    e.configure({"alg": "PS256"})
    p = seg({"sub": "x"})
    assert e.verify(f"{seg({'alg': 'PS256'})}.{p}.{b64(b'sig')}")["sub"] == "x"
    with pytest.raises(UnauthorizedError):
        e.verify(f"{seg({'alg': 'RS256'})}.{p}.{b64(b'sig')}")


# --------------------------------------------------------------------------
# The HS256 confusion path (environment/samples/hs256_confusion_vector.json)
# --------------------------------------------------------------------------

def test_hs256_path_uses_rsa_pub_not_hmac_key():
    """The confused key is the RSA public key, not the configured HMAC secret."""
    e = JwtKeyConfusionEngine({"hmac_key": b"hmac-secret", "rsa_pub": b"PUBKEY"})
    e.configure({"alg": "HS256"})
    h, p = seg({"alg": "HS256"}), seg({"sub": "x"})
    with_hmac_key = b64(
        hmac.new(b"hmac-secret", f"{h}.{p}".encode(), hashlib.sha256).digest())
    with pytest.raises(UnauthorizedError):
        e.verify(f"{h}.{p}.{with_hmac_key}")
    with_pub = b64(hmac.new(b"PUBKEY", f"{h}.{p}".encode(), hashlib.sha256).digest())
    assert e.verify(f"{h}.{p}.{with_pub}")["sub"] == "x"


def test_hs256_signing_input_is_header_dot_payload():
    """The signed input is the two encoded segments joined by a literal '.'."""
    e = JwtKeyConfusionEngine({"hmac_key": b"k", "rsa_pub": b"PUBKEY"})
    e.configure({"alg": "HS256"})
    h, p = seg({"alg": "HS256"}), seg({"sub": "x"})
    for wrong in (f"{h}{p}", p, h, f"{h}.{p}."):
        bad = b64(hmac.new(b"PUBKEY", wrong.encode(), hashlib.sha256).digest())
        with pytest.raises(UnauthorizedError):
            e.verify(f"{h}.{p}.{bad}")
    good = b64(hmac.new(b"PUBKEY", f"{h}.{p}".encode(), hashlib.sha256).digest())
    assert e.verify(f"{h}.{p}.{good}")["sub"] == "x"


# --------------------------------------------------------------------------
# Key-confusion policy (environment/docs/key-confusion-policy.md)
# --------------------------------------------------------------------------

def test_kty_is_leading_token_not_substring():
    """'HMAC key wrapped by RSA KEK' is an oct key: wrapping is not confusion."""
    assert detect_key_confusion("HS256", "HMAC key wrapped by RSA KEK") is False
    assert detect_key_confusion(
        "HS256", "oct session key; transported under RSA-OAEP") is False
    assert detect_key_confusion("HS256", "RSA-PSS public key (rotated 2025-11)") is True


def test_confusion_covers_ec_and_okp_kty():
    """EC and OKP are asymmetric families too, and 'oct'/'octet' are not."""
    assert detect_key_confusion("HS256", "EC P-256 verification key") is True
    assert detect_key_confusion("HS256", "ec secp384r1 public key") is True
    assert detect_key_confusion("HS256", "OKP Ed25519 public key") is True
    assert detect_key_confusion("HS256", "octet-sequence secret") is False
    assert detect_key_confusion("HS256", "oct") is False


def test_confusion_covers_hs384_and_hs512_alg_family():
    """The HMAC family is HS256/HS384/HS512, not HS256 alone."""
    assert detect_key_confusion("HS384", "EC P-256 verification key") is True
    assert detect_key_confusion("HS512", "OKP Ed25519 public key") is True
    assert detect_key_confusion("HS384", "RSA public key") is True
    assert detect_key_confusion("HS512", "oct secret") is False


def test_confusion_false_for_non_hmac_algs():
    """Only HMAC-family algs can be confused; asymmetric alg + asymmetric key
    is the normal case, and unknown algs are never flagged."""
    for alg in ("RS256", "RS512", "PS256", "ES256", "none", "", "HS255"):
        assert detect_key_confusion(alg, "RSA public key") is False
    assert detect_key_confusion("HS256", "") is False
