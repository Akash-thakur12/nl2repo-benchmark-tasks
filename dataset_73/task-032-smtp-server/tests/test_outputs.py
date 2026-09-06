import pytest
from engine.engine import SmtpServerEngine


@pytest.fixture
def e():
    return SmtpServerEngine()


def code(reply):
    return reply[0]


def test_greeting(e):
    assert code(e.greeting()) == 220


def test_helo(e):
    c, msg = e.feed("HELO mail.example.com")
    assert c == 250 and e.state == "GREETED"


def test_ehlo(e):
    assert code(e.feed("EHLO host")) == 250 and e.state == "GREETED"


def test_helo_requires_hostname(e):
    assert code(e.feed("HELO")) == 501


def test_full_transaction(e):
    assert code(e.feed("HELO x")) == 250
    assert code(e.feed("MAIL FROM:<a@b>")) == 250
    assert e.mail_from == "<a@b>"
    assert code(e.feed("RCPT TO:<c@d>")) == 250
    assert code(e.feed("RCPT TO:<e@f>")) == 250
    assert e.recipients == ["<c@d>", "<e@f>"]
    assert code(e.feed("DATA")) == 354 and e.state == "DATA"
    assert e.feed("Subject: hi") == (0, "")
    assert e.feed("body line") == (0, "")
    assert code(e.feed(".")) == 250 and e.state == "GREETED"
    assert e.message == ["Subject: hi", "body line"]


def test_data_dot_unstuffing(e):
    e.feed("HELO x"); e.feed("MAIL FROM:<a>"); e.feed("RCPT TO:<b>"); e.feed("DATA")
    e.feed("..leading dot")
    e.feed(".")
    assert e.message == [".leading dot"]


def test_mail_before_helo_is_503(e):
    assert code(e.feed("MAIL FROM:<a>")) == 503


def test_rcpt_before_mail_is_503(e):
    e.feed("HELO x")
    assert code(e.feed("RCPT TO:<c>")) == 503


def test_data_before_rcpt_is_503(e):
    e.feed("HELO x")
    e.feed("MAIL FROM:<a>")
    assert code(e.feed("DATA")) == 503


def test_mail_without_from_keyword_is_501(e):
    e.feed("HELO x")
    assert code(e.feed("MAIL <a>")) == 501


def test_rcpt_without_to_keyword_is_501(e):
    e.feed("HELO x")
    e.feed("MAIL FROM:<a>")
    assert code(e.feed("RCPT <c>")) == 501


def test_unknown_command_is_500(e):
    assert code(e.feed("XYZZY foo")) == 500


def test_noop_keeps_state(e):
    e.feed("HELO x")
    e.feed("MAIL FROM:<a>")
    assert e.feed("NOOP") == (250, "OK")
    assert e.state == "MAIL"


def test_rset_aborts_transaction(e):
    e.feed("HELO x")
    e.feed("MAIL FROM:<a>")
    e.feed("RCPT TO:<c>")
    assert code(e.feed("RSET")) == 250
    assert e.state == "GREETED" and e.mail_from is None and e.recipients == []


def test_rset_from_init_stays_init(e):
    # fresh engine, no HELO -> state INIT; RSET must not advance to GREETED
    assert e.state == "INIT"
    assert e.feed("RSET") == (250, "OK")
    assert e.state == "INIT"
    assert e.mail_from is None and e.recipients == [] and e.message == []


def test_quit(e):
    assert e.feed("QUIT") == (221, "Bye")
    assert e.state == "QUIT"


def test_vrfy_is_252(e):
    assert code(e.feed("VRFY someone")) == 252


@pytest.mark.parametrize("cmd", ["STARTTLS", "AUTH LOGIN", "EXPN list"])
def test_unimplemented_verbs_are_502(e, cmd):
    assert code(e.feed(cmd)) == 502


def test_helo_resets_transaction_state(e):
    e.feed("HELO a")
    e.feed("MAIL FROM:<x>")
    e.feed("RCPT TO:<y>")
    assert code(e.feed("HELO b")) == 250
    assert e.state == "GREETED" and e.mail_from is None and e.recipients == []


def test_reset_and_configure(e):
    e.feed("HELO x")
    e.feed("MAIL FROM:<a>")
    e.reset()
    assert e.state == "INIT" and e.mail_from is None
    e.feed("HELO y")
    e.configure({})
    assert e.state == "INIT" and e.mail_from is None


def test_commands_are_case_insensitive(e):
    assert code(e.feed("helo mail.example.com")) == 250 and e.state == "GREETED"
    assert code(e.feed("Mail From:<a@b>")) == 250 and e.state == "MAIL"
    assert code(e.feed("rcpt To:<c@d>")) == 250 and e.state == "RCPT"
    assert code(e.feed("DaTa")) == 354 and e.state == "DATA"
    assert code(e.feed(".")) == 250
    assert code(e.feed("QuIt")) == 221
