import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from engine.engine import AuthTokenEngine


# --------------------------------------------------------------------------- #
# Locating the shipped environment data. In a repo checkout it is a sibling of
# tests/; in the container image the data dirs are copied next to /app/engine.
# --------------------------------------------------------------------------- #
def _find_data_root():
    candidates = []
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "environment")
        candidates.append(parent)
    candidates.append(Path("/app"))
    for root in candidates:
        if (root / "reference" / "keyring.json").is_file():
            return root
    raise RuntimeError("could not locate the environment data (reference/keyring.json)")


DATA = _find_data_root()
KEYRING = json.loads((DATA / "reference" / "keyring.json").read_text(encoding="utf-8"))


def _load_captures(name):
    rows = []
    with (DATA / "capture" / name).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _mac(key, msg, trunc=8):
    return hmac.new(key, msg, hashlib.sha256).digest()[:trunc]


def _secret(kid):
    for row in KEYRING["keys"]:
        if row["kid"] == kid:
            return bytes.fromhex(row["secret_hex"])
    raise KeyError(kid)


# Epoch anchors, from reference/keyring.json width_history.
T2019 = 1546300800   # tokend-2019m rollout
THARD = 1656633600   # tokend-2021h 4 -> 8 (SEC-118)
TROLL = 1669852800   # tokend-2021h 8 -> 4 (rollback)
TREV = 1670371200    # tokend-2021h 4 -> 8 (revert)


# =========================================================================== #
# Legacy mode -- the 8 original tests, unchanged in behaviour.
# =========================================================================== #
def test_sign_verify_roundtrip():
    """Legacy: sign truncates to config['trunc'] and verify accepts it."""
    e = AuthTokenEngine({"key": b"k" * 8, "trunc": 8})
    tok = e.sign(b"h")
    assert len(tok) == 8
    assert e.verify(b"h", tok) is True
    assert e.verify(b"h!", tok) is False


def test_sign_is_deterministic():
    """Legacy: sign is a pure function of key and message."""
    e = AuthTokenEngine({"key": b"secret12", "trunc": 8})
    assert e.sign(b"ping") == e.sign(b"ping") == _mac(b"secret12", b"ping")


def test_str_key_is_utf8_encoded_same_as_bytes():
    """Legacy: a str key is UTF-8 encoded to match the bytes spelling."""
    e_str = AuthTokenEngine({"key": "secret12", "trunc": 8})
    e_bytes = AuthTokenEngine({"key": b"secret12", "trunc": 8})
    msg = b"hello world"
    assert e_str.sign(msg) == e_bytes.sign(msg) == _mac(b"secret12", msg)


def test_truncation_length_follows_config():
    """Legacy: trunc controls tag length and verify honours it."""
    e = AuthTokenEngine({"key": b"secret12", "trunc": 4})
    assert len(e.sign(b"ping")) == 4
    assert e.verify(b"ping", _mac(b"secret12", b"ping", 4)) is True


def test_recover_key_from_samples():
    """Legacy: recover_key finds the signing key among candidates."""
    real = b"mykey12"
    e = AuthTokenEngine({"trunc": 8})
    for i in range(5):
        m = f"m{i}".encode()
        e.add_sample(m, _mac(real, m).hex())
    assert e.recover_key([b"wrong1", b"wrong2", b"mykey12", b"x" * 8]) == real


def test_recover_key_returns_none_when_no_candidate_matches():
    """Legacy: recover_key returns None when nothing matches."""
    real = b"mykey12"
    e = AuthTokenEngine({"trunc": 8})
    for i in range(3):
        m = f"m{i}".encode()
        e.add_sample(m, _mac(real, m).hex())
    assert e.recover_key([b"nope0000", b"alsowrong", b"x" * 8]) is None


def test_recover_key_without_samples_returns_none():
    """Legacy: recover_key with no samples returns None."""
    e = AuthTokenEngine({"trunc": 8})
    assert e.recover_key([b"mykey12", b"x" * 8]) is None


def test_reset_and_configure_clear_samples():
    """Legacy: reset and configure both clear recorded samples."""
    real = b"mykey12"
    e = AuthTokenEngine({"trunc": 8})
    e.add_sample(b"m0", _mac(real, b"m0").hex())
    e.reset()
    assert e.recover_key([b"mykey12"]) is None
    e.add_sample(b"m0", _mac(real, b"m0").hex())
    e.configure({})
    assert e.recover_key([b"mykey12"]) is None


# =========================================================================== #
# Crux I -- tag_width_at resolves the width in force at the event's instant.
# =========================================================================== #
def _engine():
    return AuthTokenEngine({"keyring": KEYRING})


def test_width_uses_history_not_current_field():
    """Crux I: an old instant resolves to its era's width, not the export's top-level mac_bytes."""
    e = _engine()
    # 2021, 4-octet era. Top-level mac_bytes for tokend-2021h is 8.
    assert e.tag_width_at("tokend-2021h", 1612137600) == 4


def test_width_backfilled_row_ordering():
    """Crux I: the initial-rollout row is appended out of order; resolution must sort by `from`."""
    e = _engine()
    # 2021-06 is before the hardening; the governing entry is the backfilled
    # initial-rollout row that sits LAST in file order.
    assert e.tag_width_at("tokend-2021h", 1622505600) == 4


def test_width_from_is_inclusive():
    """Crux I: `from` is inclusive; the changeover second already uses the new width."""
    e = _engine()
    assert e.tag_width_at("tokend-2021h", THARD - 1) == 4
    assert e.tag_width_at("tokend-2021h", THARD) == 8


def test_width_non_monotonic_rollback():
    """Crux I: widths are not monotonic; inside the rollback week the width is 4, not max-so-far 8."""
    e = _engine()
    assert e.tag_width_at("tokend-2021h", 1670000000) == 4
    assert e.tag_width_at("tokend-2021h", TROLL) == 4
    assert e.tag_width_at("tokend-2021h", TREV - 1) == 4
    assert e.tag_width_at("tokend-2021h", TREV) == 8


def test_width_before_first_entry_is_none():
    """Crux I: before a key's earliest entry no width is in force -> None."""
    e = _engine()
    assert e.tag_width_at("tokend-2019m", T2019 - 1) is None
    assert e.tag_width_at("tokend-2019m", T2019) == 2


def test_width_unknown_kid_is_none():
    """Crux I: an unknown kid has no width -> None."""
    e = _engine()
    assert e.tag_width_at("tokend-does-not-exist", 1670000000) is None


# =========================================================================== #
# Crux I + II -- audit replays the capture corpus verdict for verdict.
# =========================================================================== #
def _all_capture_rows():
    rows = []
    for name in ("verify-01-eras.jsonl", "verify-02-rollback.jsonl",
                 "verify-03-forgeries.jsonl"):
        rows.extend(_load_captures(name))
    return rows


@pytest.mark.parametrize("record", _all_capture_rows(),
                         ids=lambda r: "%s@%d:%s" % (r["kid"], r["captured_at"], r["verdict"]))
def test_audit_matches_corpus(record):
    """Cruxes I+II: every shipped capture line replays to its recorded verdict."""
    e = _engine()
    assert e.audit(record) == record["verdict"]


def test_audit_padded_forgery_is_bad_tag():
    """Crux II: a 3-correct-octet tag zero-filled to 8 is bad-tag at the 4-octet width, not ok."""
    e = _engine()
    msg = b"POST /v1/transfer\x00acct=8811\x00amt=250"
    presented = _mac(_secret("tokend-2021h"), msg, 3).hex() + "00" * 5
    record = {"kid": "tokend-2021h", "captured_at": 1612137600,
              "msg_b64": base64.b64encode(msg).decode(), "tag_hex": presented}
    assert e.audit(record) == "bad-tag"


def test_audit_genuine_tag_ending_in_zero_is_ok():
    """Crux II: a genuine 4-octet tag whose last octet is 0x00 is ok; trailing zeros are not padding."""
    e = _engine()
    msg = b"GET /v1/balance?acct=365"
    tag = _mac(_secret("tokend-2021h"), msg, 4)
    assert tag[3] == 0  # the case only bites because this really ends in zero
    record = {"kid": "tokend-2021h", "captured_at": 1612137600,
              "msg_b64": base64.b64encode(msg).decode(),
              "tag_hex": (tag + b"\x00" * 4).hex()}
    assert e.audit(record) == "ok"


def test_audit_nonzero_pad_is_malformed():
    """Crux II: a non-zero octet in the pad region is malformed, never bad-tag or ok."""
    e = _engine()
    msg = b"GET /v1/balance?acct=1001"
    tag = _mac(_secret("tokend-2021h"), msg, 4)
    record = {"kid": "tokend-2021h", "captured_at": 1612137600,
              "msg_b64": base64.b64encode(msg).decode(),
              "tag_hex": tag.hex() + "deadbeef"}
    assert e.audit(record) == "malformed"


def test_audit_wrong_frame_length_is_malformed():
    """Crux II: the frame is a fixed 8 octets; any other length is malformed."""
    e = _engine()
    msg = b"GET /v1/balance?acct=77"
    tag6 = _mac(_secret("tokend-2021h"), msg, 6).hex()
    record = {"kid": "tokend-2021h", "captured_at": 1667260800,
              "msg_b64": base64.b64encode(msg).decode(), "tag_hex": tag6}
    assert e.audit(record) == "malformed"


def test_audit_unknown_kid_precedes_frame_checks():
    """Cruxes I+II: an unknown kid is unknown-kid even with a junk frame (check order)."""
    e = _engine()
    record = {"kid": "tokend-nope", "captured_at": 1612137600,
              "msg_b64": base64.b64encode(b"x").decode(), "tag_hex": "abcd"}
    assert e.audit(record) == "unknown-kid"


def test_audit_no_epoch_precedes_frame_checks():
    """Cruxes I+II: a known kid with no width in force is no-epoch even with a junk frame."""
    e = _engine()
    record = {"kid": "tokend-2019m", "captured_at": T2019 - 100000,
              "msg_b64": base64.b64encode(b"MTR 0007 read=1").decode(),
              "tag_hex": "zzzz"}
    assert e.audit(record) == "no-epoch"


def test_audit_rollback_week_line_is_ok_at_width_four():
    """Cruxes I+II: a mid-rollback-week frame is ok only when compared at width 4."""
    e = _engine()
    msg = b"MTR 4410 read=118"
    tag = _mac(_secret("tokend-2021h"), msg, 4)
    record = {"kid": "tokend-2021h", "captured_at": 1670000000,
              "msg_b64": base64.b64encode(msg).decode(),
              "tag_hex": (tag + b"\x00" * 4).hex()}
    assert e.audit(record) == "ok"


# =========================================================================== #
# Crux III -- recovery: unique by material, per-sample epoch width, drops.
# =========================================================================== #
def test_recover_ambiguous_two_octet_returns_none():
    """Crux III: two distinct materials fit a 2-octet evidence set -> non-answer (None)."""
    job = next(j for j in _load_captures("recovery-01-jobs.jsonl")
               if j["job"] == "2019-08-recovery")
    e = AuthTokenEngine({"keyring": KEYRING})
    for s in job["samples"]:
        e.add_sample(base64.b64decode(s["msg_b64"]), s["tag_hex"],
                     {"kid": s["kid"], "captured_at": s["captured_at"]})
    candidates = [bytes.fromhex(c["secret_hex"]) for c in job["candidates"]]
    assert e.recover_key(candidates) is None


def test_matching_keys_lists_all_matches():
    """Crux III: matching_keys returns every match in candidate order (the ambiguous pair)."""
    job = next(j for j in _load_captures("recovery-01-jobs.jsonl")
               if j["job"] == "2019-08-recovery")
    e = AuthTokenEngine({"keyring": KEYRING})
    for s in job["samples"]:
        e.add_sample(base64.b64decode(s["msg_b64"]), s["tag_hex"],
                     {"kid": s["kid"], "captured_at": s["captured_at"]})
    candidates = [bytes.fromhex(c["secret_hex"]) for c in job["candidates"]]
    matches = e.matching_keys(candidates)
    assert len(matches) == 2
    assert set(matches) == {candidates[0], candidates[1]}


def test_recover_duplicate_material_returns_key():
    """Crux III: the same material matched twice (two regional kids) is still one answer."""
    secret = _secret("tokend-eu1")
    e = AuthTokenEngine({"keyring": KEYRING})
    msgs = [b"POST /v1/transfer\x00acct=8811\x00amt=250",
            b"POST /v1/transfer\x00acct=8811\x00amt=1400"]
    for m in msgs:
        e.add_sample(m, (_mac(secret, m, 8) + b"").hex(),
                     {"kid": "tokend-eu1", "captured_at": 1675209600})
    # candidate list mixes bytes and str spellings of the same material
    result = e.recover_key([secret, secret.decode()])
    assert result in (secret, secret.decode())


def test_recover_mixed_era_uses_per_sample_width():
    """Crux III+I: a 4-octet and an 8-octet sample recover the key only at each own width."""
    secret = _secret("tokend-2021h")
    e = AuthTokenEngine({"keyring": KEYRING})
    m4 = b"POST /v1/transfer\x00acct=8811\x00amt=250"
    m8 = b"POST /v1/transfer\x00acct=8811\x00amt=1400"
    e.add_sample(m4, (_mac(secret, m4, 4) + b"\x00" * 4).hex(),
                 {"kid": "tokend-2021h", "captured_at": 1670000000})   # rollback wk, w=4
    e.add_sample(m8, _mac(secret, m8, 8).hex(),
                 {"kid": "tokend-2021h", "captured_at": 1670457600})   # after revert, w=8
    other = _secret("tokend-2023r")
    assert e.recover_key([other, secret]) == secret


def test_recover_unresolvable_samples_are_dropped():
    """Crux III: samples with no resolvable width are excluded, not counted as mismatches."""
    secret = _secret("tokend-2021h")
    e = AuthTokenEngine({"keyring": KEYRING})
    m8 = b"GET /v1/balance?acct=8"
    e.add_sample(m8, _mac(secret, m8, 8).hex(),
                 {"kid": "tokend-2021h", "captured_at": 1670457600})   # usable, w=8
    e.add_sample(b"GET /v1/balance?acct=3",
                 (_mac(secret, b"GET /v1/balance?acct=3", 4) + b"\x00" * 4).hex(),
                 {"kid": "tokend-2021h", "captured_at": 1600000000})   # pre-epoch, dropped
    e.add_sample(b"GET /v1/balance?acct=4", "00" * 8,
                 {"kid": "tokend-nope", "captured_at": 1670000000})    # unknown kid, dropped
    assert e.recover_key([_secret("tokend-2023r"), secret]) == secret


def test_recover_no_usable_samples_returns_none():
    """Crux III: when every sample is unresolvable there is no evidence -> None."""
    e = AuthTokenEngine({"keyring": KEYRING})
    e.add_sample(b"GET /v1/balance?acct=4", "00" * 8,
                 {"kid": "tokend-nope", "captured_at": 1670000000})
    assert e.recover_key([_secret("tokend-2021h")]) is None


# =========================================================================== #
# Keyring-mode sign / verify.
# =========================================================================== #
def test_keyring_sign_uses_epoch_width():
    """Keyring: sign truncates to the width in force at the configured clock instant."""
    ts = [1612137600]  # 4-octet era
    e = AuthTokenEngine({"keyring": KEYRING, "kid": "tokend-2021h",
                         "clock": lambda: ts[0]})
    msg = b"GET /v1/balance?acct=1001"
    assert e.sign(msg) == _mac(_secret("tokend-2021h"), msg, 4)
    ts[0] = 1667260800  # 8-octet era
    assert e.sign(msg) == _mac(_secret("tokend-2021h"), msg, 8)


def test_keyring_verify_rejects_nonzero_pad():
    """Keyring: verify accepts the zero-padded frame and rejects a non-zero pad."""
    e = AuthTokenEngine({"keyring": KEYRING, "kid": "tokend-2021h",
                         "clock": lambda: 1612137600})
    msg = b"GET /v1/balance?acct=1001"
    tag = _mac(_secret("tokend-2021h"), msg, 4)
    assert e.verify(msg, tag) is True
    assert e.verify(msg, tag + b"\x00" * 4) is True
    assert e.verify(msg, tag + b"\x01" + b"\x00" * 3) is False
