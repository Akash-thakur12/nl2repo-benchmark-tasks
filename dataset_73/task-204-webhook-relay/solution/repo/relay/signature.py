"""Signature header parsing and verification (spec section 2)."""
import hashlib
import hmac


class Malformed(Exception):
    """The header could not be understood at all (2.4)."""


def parse_header(header):
    """2.1: a comma-separated list of name=value pairs, exactly one t, at least
    one v1, unknown names ignored."""
    if not isinstance(header, str) or header == "":
        raise Malformed("empty signature header")

    timestamp = None
    offered = []
    for pair in header.split(","):
        if "=" not in pair:
            raise Malformed("pair without a separator: %r" % pair)
        name, _, value = pair.partition("=")
        name = name.strip()
        if name == "t":
            if timestamp is not None:
                raise Malformed("more than one timestamp")
            try:
                timestamp = int(value)
            except ValueError:
                raise Malformed("timestamp is not an integer")
        elif name == "v1":
            offered.append(value)

    if timestamp is None:
        raise Malformed("no timestamp")
    if not offered:
        raise Malformed("no v1 signature")
    return timestamp, offered


def in_force(secrets, retired, timestamp):
    """2.3: a key may carry a retirement instant. The signature was produced by
    whatever authority held when the request was signed, so the header timestamp
    picks the key set - not the relay clock. That is the in-flight grace every
    rotation needs: a request signed just before the cutover still verifies
    however late it reaches us, and one signed after it never does.
    Retirement is inclusive: a signature stamped exactly at the instant still
    verifies."""
    return {key_id: secret for key_id, secret in secrets.items()
            if key_id not in retired or timestamp <= retired[key_id]}


def verify(secrets, retired, timestamp, body, offered):
    """2.2, 2.3: sign "<t>.<body>" with each secret still in force for that
    timestamp; any offered v1 may match any of them, which is what lets a key be
    rotated live."""
    signed = "{}.{}".format(timestamp, body)
    message = signed.encode("utf-8")
    for secret in in_force(secrets, retired, timestamp).values():
        candidate = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        for value in offered:
            if hmac.compare_digest(candidate, value):
                return True
    return False
