from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class SmtpServerEngine:
    """RFC 5321 SMTP session state machine. See instruction.md."""

    CMDS = {"HELO", "EHLO", "MAIL", "RCPT", "DATA", "QUIT", "RSET", "NOOP",
            "STARTTLS", "AUTH", "VRFY", "EXPN"}

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def greeting(self):
        raise NotImplementedError(_STUB)

    def feed(self, line):
        raise NotImplementedError(_STUB)
