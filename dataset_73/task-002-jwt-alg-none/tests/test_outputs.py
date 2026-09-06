import base64
import json
import time

import pytest
from engine.engine import JwtAlgNoneEngine, UnauthorizedError, ValidationError


def _seg(obj):
    return base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()


def test_roundtrip():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    t = e.issue({"sub": "alice"})
    claims = e.verify(t)
    assert claims["sub"] == "alice"
    assert "iat" in claims and "exp" in claims
    assert claims["exp"] > claims["iat"]


def test_ttl_controls_expiry_claim():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    claims = e.verify(e.issue({"sub": "x"}, ttl=10))
    assert claims["exp"] - claims["iat"] == 10


def test_alg_none_rejected():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    h = _seg({"alg": "none", "typ": "JWT"})
    p = _seg({"sub": "x", "exp": 9999999999})
    with pytest.raises(UnauthorizedError):
        e.verify(f"{h}.{p}.")
    assert e.accept_unsigned(f"{h}.{p}.") is False


@pytest.mark.parametrize("alg", ["none", "NONE", "None", "nOnE", "nonE"])
def test_alg_none_rejected_any_case(alg):
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    h = _seg({"alg": alg, "typ": "JWT"})
    p = _seg({"sub": "x", "exp": 9999999999})
    with pytest.raises(UnauthorizedError):
        e.verify(f"{h}.{p}.")
    assert e.accept_unsigned(f"{h}.{p}.") is False


def test_alg_switch_rejected():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    good = e.issue({"sub": "x"})
    _, p, s = good.split(".")
    forged = f'{_seg({"alg": "HS512", "typ": "JWT"})}.{p}.{s}'
    with pytest.raises(UnauthorizedError):
        e.verify(forged)


def test_bad_sig():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    t = e.issue({"sub": "bob"})
    parts = t.split(".")
    parts[2] = "A" * len(parts[2])
    with pytest.raises(UnauthorizedError):
        e.verify(".".join(parts))


def test_expired():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    t = e.issue({"sub": "x", "exp": 1})
    with pytest.raises(UnauthorizedError):
        e.verify(t)


@pytest.mark.parametrize("token", ["", "only-one-part", "two.parts", "!!!.@@@.###"])
def test_malformed_token_raises_validation_error(token):
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    with pytest.raises(ValidationError):
        e.verify(token)


def test_accept_unsigned_is_always_false():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    signed = e.issue({"sub": "x"})
    unsigned = f'{_seg({"alg": "none"})}.{_seg({"sub": "x"})}.'
    assert e.accept_unsigned(signed) is False
    assert e.accept_unsigned(unsigned) is False


def test_reset_and_configure():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    t = e.issue({"sub": "x"})
    e.reset()                       # algorithm pin back to HS256, key unchanged
    assert e.verify(t)["sub"] == "x"
    e.configure({"key": b"rotated-key-value-000"})
    with pytest.raises(UnauthorizedError):
        e.verify(t)                 # old token no longer verifies under new key
    assert e.verify(e.issue({"sub": "y"}))["sub"] == "y"


def test_configure_changes_pinned_algorithm():
    e = JwtAlgNoneEngine({"key": b"k" * 32})
    old = e.issue({"sub": "x"})              # header declares alg=HS256
    e.configure({"alg": "HS384"})
    with pytest.raises(UnauthorizedError):
        e.verify(old)                        # HS256 != pinned HS384 -> rejected
    fresh = e.issue({"sub": "y"})            # now declares alg=HS384
    assert e.verify(fresh)["sub"] == "y"


# =====================================================================
# Fixtures shared by the rotation / algorithm / reason-code tests below.
# Tokens are minted here with plain hmac + hashlib rather than through the
# engine, so these tests state what a token IS rather than echoing whatever
# the implementation happens to produce.
# =====================================================================

import hashlib
import hmac

_DIGESTS = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}

NOV01 = 1698796800   # k1 activated
DEC01 = 1701388800
DEC25 = 1703462400   # k2 activated -- rotation overlap starts
DEC28 = 1703721600   # inside the overlap
DEC31 = 1703980800   # inside the overlap
JAN01 = 1704067200   # k1 retired
FEB01 = 1706745600   # k2 retired, k1 re-activated (rollback)
FEB04 = 1707004800   # inside k1's second window
FEB08 = 1707350400   # k1 retired again, k3 activated
FEB20 = 1708387200
MAR01 = 1709251200   # "now" for most of these tests
OCT01 = 1696118400   # before anything on the ring was activated

K1 = b"ring-secret-k1-2b7c"
K2 = b"ring-secret-k2-8f3a"
K3 = b"ring-secret-k3-c41d"

# Appended in the order the rotation tickets closed, which is not the order
# the keys came into force, and k1 owns two disjoint stretches.
RING = [
    {"kid": "k1", "secret": K1, "activated": NOV01, "retired": JAN01},
    {"kid": "k3", "secret": K3, "activated": FEB08, "retired": None},
    {"kid": "k2", "secret": K2, "activated": DEC25, "retired": FEB01},
    {"kid": "k1", "secret": K1, "activated": FEB01, "retired": FEB08},
]

FAR = 4102444800     # an exp that never bites
SINGLE = b"corpus-hs-secret-9a1"


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _mint(header, claims, secret, digest=None):
    """A compact JWT, built without reference to the engine under test."""
    h = _seg(header)
    p = _seg(claims)
    mac = hmac.new(secret, f"{h}.{p}".encode(), digest or _DIGESTS[header["alg"]])
    return f"{h}.{p}.{_b64(mac.digest())}"


def _ring_engine(clock=MAR01, **extra):
    config = {"keyring": [dict(e) for e in RING], "clock": lambda: clock}
    config.update(extra)
    return JwtAlgNoneEngine(config)


def _key_engine(clock=MAR01, key=SINGLE):
    return JwtAlgNoneEngine({"key": key, "clock": lambda: clock})


def _ring_token(kid, secret, iat, exp=FAR, alg="HS256", digest=None):
    return _mint({"alg": alg, "typ": "JWT", "kid": kid},
                 {"iat": iat, "exp": exp, "sub": "svc-edge"}, secret, digest)


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


# ---------------------------------------------------------------------
# Keyring: which secret was in force, and when
# ---------------------------------------------------------------------

def test_keyring_supersedes_the_single_key():
    """config['keyring'], when present, replaces config['key'] entirely."""
    e = _ring_engine(key=SINGLE)
    assert e.verify(_ring_token("k3", K3, FEB20))["sub"] == "svc-edge"
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_ring_token("k3", SINGLE, FEB20))
    assert _code(exc) == "sig_mismatch"


def test_issue_stamps_the_kid_of_the_key_that_signed():
    """A token minted under a keyring carries that entry's kid in its header."""
    e = _ring_engine(clock=MAR01)
    token = e.issue({"sub": "alice"})
    header = json.loads(base64.urlsafe_b64decode(
        token.split(".")[0] + "=" * (-len(token.split(".")[0]) % 4)))
    assert header["kid"] == "k3"
    h, p, s = token.split(".")
    expected = hmac.new(K3, f"{h}.{p}".encode(), hashlib.sha256).digest()
    assert s == _b64(expected)


def test_issue_picks_the_latest_activated_unretired_entry():
    """During a rotation overlap the newer of the two live keys mints."""
    # At DEC31 both k1 (activated NOV01) and k2 (activated DEC25) are
    # un-retired. k1 is listed first; k2 is the one that came into force last.
    e = _ring_engine(clock=DEC31)
    token = e.issue({"sub": "bob"}, ttl=900)
    h, p, s = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(h + "=" * (-len(h) % 4)))
    assert header["kid"] == "k2"
    assert s == _b64(hmac.new(K2, f"{h}.{p}".encode(), hashlib.sha256).digest())


def test_issue_without_an_active_key_is_refused():
    """Minting with nothing in force fails loudly rather than falling back."""
    e = _ring_engine(clock=OCT01)
    with pytest.raises(UnauthorizedError) as exc:
        e.issue({"sub": "dave"})
    assert _code(exc) == "no_active_key"



# The staging fleet runs its own two-entry ring; it is the only ring on which
# the retirement instant is observable at mint time, because there the entry
# that is retiring is also the one that came into force most recently.
STAGING = [
    {"kid": "s1", "secret": b"staging-secret-s1-11aa",
     "activated": 1700000000, "retired": None},
    {"kid": "s2", "secret": b"staging-secret-s2-22bb",
     "activated": 1700086400, "retired": 1700172800},
]


def test_a_key_is_in_force_from_its_activation_second():
    """`activated` is inclusive: the key mints from that exact second on."""
    e = _ring_engine(clock=FEB08)          # k3's activation instant exactly
    h = e.issue({"sub": "gale"}).split(".")[0]
    header = json.loads(base64.urlsafe_b64decode(h + "=" * (-len(h) % 4)))
    assert header["kid"] == "k3"


def test_a_key_is_done_at_its_retirement_second():
    """`retired` is exclusive: the key does not mint on that second."""
    e = JwtAlgNoneEngine({"keyring": [dict(x) for x in STAGING],
                          "clock": lambda: 1700172800})
    h = e.issue({"sub": "harry"}).split(".")[0]
    header = json.loads(base64.urlsafe_b64decode(h + "=" * (-len(h) % 4)))
    assert header["kid"] == "s1"


def test_verify_accepts_a_token_minted_before_its_key_retired():
    """A token stays good for its life even after the key that signed it retires."""
    e = _ring_engine(clock=MAR01)          # two months after k1 was retired
    claims = e.verify(_ring_token("k1", K1, DEC01))
    assert claims["iat"] == DEC01


def test_verify_rejects_a_fresh_token_bearing_a_retired_kid():
    """A leaked retired secret must not mint new tokens: the iat is checked."""
    e = _ring_engine(clock=MAR01)
    # byte-correct k1 MAC, but minted now -- long after k1 last held the ring
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_ring_token("k1", K1, MAR01 - 100))
    assert _code(exc) == "key_window"


def test_verify_accepts_both_windows_of_a_rolled_back_kid():
    """k1 owns two disjoint windows; tokens from either one verify."""
    e = _ring_engine(clock=MAR01)
    assert e.verify(_ring_token("k1", K1, DEC01))["iat"] == DEC01
    assert e.verify(_ring_token("k1", K1, FEB04))["iat"] == FEB04


def test_verify_rejects_a_kid_between_its_two_windows():
    """k1 held nothing in January; a token dated then is not accepted."""
    e = _ring_engine(clock=MAR01)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_ring_token("k1", K1, JAN01 + 3600))
    assert _code(exc) == "key_window"


def test_overlapping_windows_are_disambiguated_by_kid():
    """Windows do not partition the timeline; the header kid picks the entry."""
    e = _ring_engine(clock=MAR01)
    assert e.verify(_ring_token("k1", K1, DEC28))["iat"] == DEC28
    assert e.verify(_ring_token("k2", K2, DEC28))["iat"] == DEC28


def test_unknown_kid_is_unauthorized_with_its_own_code():
    """A kid the ring has never held is an auth failure, not a malformed token."""
    e = _ring_engine(clock=MAR01)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_ring_token("k9", K3, FEB20))
    assert _code(exc) == "unknown_kid"


def test_missing_kid_under_a_keyring_is_unknown_kid():
    """With a ring in force a header carrying no kid names no key."""
    e = _ring_engine(clock=MAR01)
    token = _mint({"alg": "HS256", "typ": "JWT"},
                  {"iat": FEB20, "exp": FAR, "sub": "svc-edge"}, K3)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(token)
    assert _code(exc) == "unknown_kid"


# ---------------------------------------------------------------------
# Clock skew: where the fleet's tolerance is spent, and where it is not
# ---------------------------------------------------------------------

def test_key_window_tolerates_activation_skew():
    """A skewed edge node may stamp an iat up to 60s before activation."""
    e = _ring_engine(clock=MAR01)
    assert e.verify(_ring_token("k3", K3, FEB08 - 60))["iat"] == FEB08 - 60


def test_key_window_skew_tolerance_stops_at_sixty_seconds():
    """One second beyond the fleet's NTP discipline is out of the window."""
    e = _ring_engine(clock=MAR01)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_ring_token("k3", K3, FEB08 - 61))
    assert _code(exc) == "key_window"


def test_key_window_tolerates_retirement_skew_exclusively():
    """The retirement end takes the same 60s of slack, exclusive at the bound."""
    e = _ring_engine(clock=MAR01)
    assert e.verify(_ring_token("k2", K2, FEB01 + 59))["iat"] == FEB01 + 59
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_ring_token("k2", K2, FEB01 + 60))
    assert _code(exc) == "key_window"


def test_skew_tolerance_does_not_extend_token_lifetime():
    """exp is compared flat against the clock: no grace, not even a second."""
    e = _ring_engine(clock=MAR01)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_ring_token("k3", K3, FEB20, exp=MAR01 - 30))
    assert _code(exc) == "expired"
    with pytest.raises(UnauthorizedError):
        e.verify(_ring_token("k3", K3, FEB20, exp=MAR01 - 1))
    assert e.verify(_ring_token("k3", K3, FEB20, exp=MAR01))["exp"] == MAR01


# ---------------------------------------------------------------------
# The alg header
# ---------------------------------------------------------------------

@pytest.mark.parametrize("alg", ["none", "NONE", "None", "nOnE", " none ",
                                 "\tnone\n", "NoNe "])
def test_unsigned_algorithm_is_matched_case_folded_and_stripped(alg):
    """The `none` guard folds case and strips surrounding whitespace."""
    e = _key_engine()
    token = f'{_seg({"alg": alg, "typ": "JWT"})}.{_seg({"sub": "x", "exp": FAR})}.'
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(token)
    assert _code(exc) == "alg_none"


@pytest.mark.parametrize("alg", ["hs256", "Hs256", "HS256 ", " HS256"])
def test_pin_is_matched_byte_exact(alg):
    """Registered algorithm names are case-sensitive: only 'HS256' is the pin."""
    e = _key_engine()
    claims = {"iat": MAR01 - 10, "exp": FAR, "sub": "svc-billing"}
    # a byte-correct HS256 MAC over this exact signing input -- only the
    # spelling of the name is wrong
    token = _mint({"alg": alg, "typ": "JWT"}, claims, SINGLE,
                  digest=hashlib.sha256)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(token)
    assert _code(exc) == "alg_pin_mismatch"


@pytest.mark.parametrize("alg", [None, ["none"], {"alg": "none"}, 256, True])
def test_non_string_alg_is_a_pin_mismatch_not_alg_none(alg):
    """A JSON null or array in `alg` names no algorithm; it is not `none`."""
    e = _key_engine()
    token = f'{_seg({"alg": alg, "typ": "JWT"})}.{_seg({"sub": "x", "exp": FAR})}.'
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(token)
    assert _code(exc) == "alg_pin_mismatch"


def test_missing_alg_is_a_pin_mismatch():
    """A header with no alg member at all is a pin mismatch."""
    e = _key_engine()
    token = f'{_seg({"typ": "JWT"})}.{_seg({"sub": "x", "exp": FAR})}.'
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(token)
    assert _code(exc) == "alg_pin_mismatch"


@pytest.mark.parametrize("alg,mac_bytes,digest",
                         [("HS256", 32, hashlib.sha256),
                          ("HS384", 48, hashlib.sha384),
                          ("HS512", 64, hashlib.sha512)])
def test_pin_selects_the_digest_used_to_sign(alg, mac_bytes, digest):
    """The pinned algorithm decides the digest, not just the header string."""
    e = _key_engine()
    e.configure({"alg": alg})
    token = e.issue({"sub": "erin"}, ttl=60)
    h, p, s = token.split(".")
    raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    assert len(raw) == mac_bytes
    assert raw == hmac.new(SINGLE, f"{h}.{p}".encode(), digest).digest()
    assert json.loads(base64.urlsafe_b64decode(h + "=" * (-len(h) % 4)))["alg"] == alg


def test_header_algorithm_must_agree_with_the_mac_digest():
    """An HS384 token carrying a SHA-256 MAC is a signature failure."""
    e = _key_engine()
    e.configure({"alg": "HS384"})
    claims = {"iat": MAR01 - 10, "exp": FAR, "sub": "svc-billing"}
    assert e.verify(_mint({"alg": "HS384", "typ": "JWT"}, claims, SINGLE))["sub"]
    bad = _mint({"alg": "HS384", "typ": "JWT"}, claims, SINGLE,
                digest=hashlib.sha256)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(bad)
    assert _code(exc) == "sig_mismatch"


@pytest.mark.parametrize("alg", ["RS256", "none", "HS1", "ES256"])
def test_configure_ignores_an_unpinnable_algorithm(alg):
    """A push naming an algorithm we cannot do is survived, not adopted."""
    e = _key_engine()
    e.configure({"alg": alg, "key": b"pushed-secret-4c2e"})
    # the pin was left alone ...
    claims = {"iat": MAR01 - 10, "exp": FAR, "sub": "svc-billing"}
    assert e.verify(_mint({"alg": "HS256", "typ": "JWT"}, claims,
                          b"pushed-secret-4c2e"))["sub"] == "svc-billing"
    # ... and the key in the same call was applied
    with pytest.raises(UnauthorizedError):
        e.verify(_mint({"alg": "HS256", "typ": "JWT"}, claims, SINGLE))


def test_configure_ignoring_a_pin_does_not_raise():
    """An unlisted pin is a logged operator mistake, never an exception."""
    e = _key_engine()
    e.configure({"alg": "RS256"})           # must not raise
    token = e.issue({"sub": "x"}, ttl=60)
    header = token.split(".")[0]
    decoded = json.loads(base64.urlsafe_b64decode(
        header + "=" * (-len(header) % 4)))
    assert decoded["alg"] == "HS256"


# ---------------------------------------------------------------------
# Reason codes: which class each rejection belongs to
# ---------------------------------------------------------------------

def test_expired_is_an_authentication_failure_not_structural_damage():
    """An expired credential raises UnauthorizedError with code 'expired'."""
    e = _key_engine()
    claims = {"iat": MAR01 - 100, "exp": MAR01 - 30, "sub": "svc-billing"}
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_mint({"alg": "HS256", "typ": "JWT"}, claims, SINGLE))
    assert _code(exc) == "expired"


def test_pin_rejection_is_reported_separately_from_signature_rejection():
    """alg_pin_mismatch and sig_mismatch are different codes on purpose."""
    e = _key_engine()
    claims = {"iat": MAR01 - 10, "exp": FAR, "sub": "svc-billing"}
    with pytest.raises(UnauthorizedError) as switched:
        e.verify(_mint({"alg": "HS512", "typ": "JWT"}, claims, SINGLE))
    good = _mint({"alg": "HS256", "typ": "JWT"}, claims, SINGLE)
    h, p, s = good.split(".")
    with pytest.raises(UnauthorizedError) as tampered:
        e.verify(f"{h}.{p}.{'A' * len(s)}")
    assert _code(switched) == "alg_pin_mismatch"
    assert _code(tampered) == "sig_mismatch"


@pytest.mark.parametrize("token,code", [
    ("", "malformed_parts"),
    ("aaa.bbb", "malformed_parts"),
    ("aaa.bbb.ccc.ddd", "malformed_parts"),
    ("!!!.@@@.###", "bad_header_b64"),
])
def test_structural_reason_codes(token, code):
    """Structural damage raises ValidationError carrying a structural code."""
    e = _key_engine()
    with pytest.raises(ValidationError) as exc:
        e.verify(token)
    assert _code(exc) == code


def test_header_that_is_not_an_object_is_rejected_structurally():
    """A header decoding to a JSON string or array is structural damage."""
    e = _key_engine()
    for header in ("HS256", ["HS256"], 7):
        with pytest.raises(ValidationError) as exc:
            e.verify(f'{_seg(header)}.{_seg({"sub": "x"})}.x')
        assert _code(exc) == "header_not_object"


def test_payload_that_is_not_an_object_is_rejected_structurally():
    """A payload that will not decode to a JSON object is structural damage."""
    e = _key_engine()
    head = _seg({"alg": "HS256", "typ": "JWT"})
    for payload in ("@@@", _seg([1, 2]), _seg("nope")):
        with pytest.raises(ValidationError) as exc:
            e.verify(f"{head}.{payload}.x")
        assert _code(exc) == "bad_payload_b64"


# ---------------------------------------------------------------------
# Ring selection and pin selection, sharpened
# (each case is a line of samples/gateway_corpus.jsonl)
# ---------------------------------------------------------------------

def test_missing_iat_under_a_keyring_is_a_key_window_failure():
    """Without an iat the ring cannot say the kid was entitled to sign."""
    e = _ring_engine(clock=MAR01)
    token = _mint({"alg": "HS256", "typ": "JWT", "kid": "k3"},
                  {"exp": FAR, "sub": "svc-edge"}, K3)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(token)
    assert _code(exc) == "key_window"


def test_ring_entry_is_selected_by_kid_not_by_trying_every_secret():
    """kid k3, inside k3's window, but the MAC was made with k1's secret."""
    e = _ring_engine(clock=MAR01)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_ring_token("k3", K1, FEB20))
    assert _code(exc) == "sig_mismatch"


def test_alg_pin_is_checked_before_the_ring_is_consulted():
    """A ring token whose only fault is its alg is a pin mismatch, not a MAC one."""
    e = _ring_engine(clock=MAR01)
    token = _mint({"alg": "HS512", "typ": "JWT", "kid": "k3"},
                  {"iat": FEB20, "exp": FAR, "sub": "svc-edge"}, K3)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(token)
    assert _code(exc) == "alg_pin_mismatch"


@pytest.mark.parametrize("alg,digest", [("HS384", hashlib.sha384),
                                        ("HS512", hashlib.sha512)])
def test_pin_selects_the_digest_used_to_verify(alg, digest):
    """The pin decides the digest on the way in, not just on the way out."""
    e = _key_engine()
    e.configure({"alg": alg})
    claims = {"iat": MAR01 - 10, "exp": FAR, "sub": "svc-billing"}
    good = _mint({"alg": alg, "typ": "JWT"}, claims, SINGLE, digest)
    assert e.verify(good)["sub"] == "svc-billing"
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(_mint({"alg": alg, "typ": "JWT"}, claims, SINGLE, hashlib.sha256))
    assert _code(exc) == "sig_mismatch"


def test_an_unlisted_pin_push_does_not_make_that_algorithm_verifiable():
    """After a push naming RS256, a header saying RS256 is still refused."""
    e = _key_engine()
    e.configure({"alg": "RS256", "key": b"pushed-secret-4c2e"})
    claims = {"iat": MAR01 - 10, "exp": FAR, "sub": "svc-billing"}
    token = _mint({"alg": "RS256", "typ": "JWT"}, claims,
                  b"pushed-secret-4c2e", digest=hashlib.sha256)
    with pytest.raises(UnauthorizedError) as exc:
        e.verify(token)
    assert _code(exc) == "alg_pin_mismatch"
