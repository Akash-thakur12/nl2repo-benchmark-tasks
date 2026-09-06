"""RFC 5321 SMTP server-side session state machine.

``feed`` takes one command / data line and returns ``(reply_code, reply_text)``.
Reply code 0 with empty text means "buffered, no reply" (data lines).
"""
from __future__ import annotations

from engine.session import (
    STATE_DATA, STATE_GREETED, STATE_INIT, STATE_MAIL, STATE_QUIT, STATE_RCPT,
)


class SmtpServerEngine:
    CMDS = {"HELO", "EHLO", "MAIL", "RCPT", "DATA", "QUIT", "RSET", "NOOP",
            "STARTTLS", "AUTH", "VRFY", "EXPN"}

    def __init__(self, config=None):
        self.reset()

    def reset(self):
        self.state = STATE_INIT
        self.mail_from = None
        self.recipients = []
        self.message = []

    def configure(self, options):
        self.reset()

    def greeting(self):
        return (220, "smtp.example.com Service ready")

    # ------------------------------------------------------------- feed
    def feed(self, line):
        if self.state == STATE_DATA:
            if line == ".":
                self.state = STATE_GREETED
                return (250, "OK: message accepted for delivery")
            self.message.append(line[1:] if line.startswith("..") else line)
            return (0, "")

        parts = line.split(" ", 1)
        cmd = parts[0].upper()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd not in self.CMDS:
            return (500, "Command not recognized")

        if cmd in ("HELO", "EHLO"):
            if not arg:
                return (501, "Syntax: HELO hostname")
            self.state = STATE_GREETED
            self.mail_from = None
            self.recipients = []
            return (250, "smtp.example.com Hello " + arg)

        if cmd == "NOOP":
            return (250, "OK")

        if cmd == "RSET":
            self.mail_from = None
            self.recipients = []
            self.message = []
            if self.state != STATE_INIT:
                self.state = STATE_GREETED
            return (250, "OK")

        if cmd == "QUIT":
            self.state = STATE_QUIT
            return (221, "Bye")

        if cmd == "VRFY":
            return (252, "Cannot VRFY user, but will accept message")

        if cmd in ("STARTTLS", "AUTH", "EXPN"):
            return (502, "Command not implemented")

        if cmd == "MAIL":
            if self.state != STATE_GREETED:
                return (503, "Bad sequence: send HELO/EHLO first (or already in a transaction)")
            if not arg.upper().startswith("FROM:"):
                return (501, "Syntax: MAIL FROM:<address>")
            self.mail_from = arg[5:].strip()
            self.state = STATE_MAIL
            return (250, "OK")

        if cmd == "RCPT":
            if self.state not in (STATE_MAIL, STATE_RCPT):
                return (503, "Bad sequence: need MAIL FROM first")
            if not arg.upper().startswith("TO:"):
                return (501, "Syntax: RCPT TO:<address>")
            self.recipients.append(arg[3:].strip())
            self.state = STATE_RCPT
            return (250, "OK")

        if cmd == "DATA":
            if self.state != STATE_RCPT:
                return (503, "Bad sequence: need RCPT TO first")
            self.state = STATE_DATA
            self.message = []
            return (354, "Start mail input; end with <CRLF>.<CRLF>")

        return (500, "Command not recognized")
