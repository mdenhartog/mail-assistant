---
intent: INT-002
feature: web-settings
---

# U-web-settings-12: Mail sender port, SMTP adapter and fake (R1)

- Layer: backend
- Contract: port `MailSender.send_code(address, code, expires_at) -> None` raising `MailError` (no cause text) on any failure; `SmtpMailSender` using `aiosmtplib` (decided here: async, STARTTLS with `start_tls=True` and certificate validation, maintained; pinned in `pyproject.toml` within the dependency cooldown); `FakeMailer` records messages. The message is plain text: the code, its validity in minutes, no link, no request details, a subject without the code. The `aiosmtplib` logger is pinned to WARNING.
- Files: `backend/app/mail/sender.py`, `backend/app/mail/smtp.py`, `backend/app/mail/message.py`, `backend/tests/mail/test_smtp.py`, `backend/pyproject.toml`
- Depends on: U-web-settings-04
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-tls-certificates
- Criteria:
  1. Given a code `424242` and an expiry, When the message is built, Then the body has the code and "valid for 10 minutes", no `http`, no `<a`, no URL, and the subject does not contain the code (AC-29, W-14) (type: security; level: unit).
  2. Given the in-process test server that offers STARTTLS with a certificate from the test CA, When a message is sent, Then it arrives after the upgrade and the credentials were sent only after it (AC-29) (type: happy; level: unit).
  3. Given a server without STARTTLS, When a message is sent, Then `MailError` and nothing was sent, no downgrade to plain text (AC-29, W-14) (type: security; level: unit).
  4. Given a server certificate from an untrusted CA or for another host name, When a message is sent, Then `MailError` (AC-29, W-14) (type: security; level: unit).
  5. Given a refused login, a timeout and a dropped connection, When sending, Then `MailError` each, whose text contains neither the address, the code, the password nor the server reply (W-15, W-16) (type: security; level: unit).
  6. Given a failing send with canaries for code and password, When logs are captured, Then no canary appears and the `aiosmtplib` logger is at WARNING (W-15, W-16) (type: security; level: unit).
  7. Given the send timeout from settings, When the server stalls, Then the call ends at the timeout with `MailError` (type: error; level: unit).
  8. Given `FakeMailer`, When used, Then it records address, code and expiry and can be told to fail (type: happy; level: unit).
