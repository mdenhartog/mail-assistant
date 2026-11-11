import importlib.util

from app.mail.sender import MailError


def test_the_old_mailer_port_is_replaced_not_kept_beside_the_new_one() -> None:
    assert importlib.util.find_spec("app.mailer") is None


def test_mail_error_carries_no_cause_text() -> None:
    error = MailError()
    assert str(error) == ""
    assert error.__cause__ is None
