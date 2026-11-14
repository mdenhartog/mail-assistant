---
intent: INT-002
feature: web-settings
---

# U-web-settings-04: Settings and start-up validation (R1)

- Layer: backend
- Contract: `Settings` gains every value the feature needs, defined once here: username, e-mail address, SMTP host, port, user, password and `smtp_starttls`, code-hash key, CSRF key, username-hash key, public origin, database URL (asyncpg, `ssl` setting), `notice_interval_minutes`, and the limits (`rate_limit_per_minute` 30, `body_limit_bytes` 8192, `code_ttl_seconds` 600, `resend_cooldown_seconds` 60, `codes_per_hour` 5, `max_attempts` 5, `open_login_request_cap`, `idle_seconds` 1800, `absolute_seconds` 43200, trusted proxy CIDRs and hops). `validate_startup(settings)` raises `ConfigurationError` naming the field, never the value; `create_app(settings, *, clock, ids, codes, mailer)` calls it. The cookie lifetimes are fixed here: `__Host-login` Max-Age 600, `__Host-session` Max-Age 43200.
- Files: `backend/app/config.py`, `backend/app/startup.py`, `backend/app/main.py`, `backend/tests/test_startup.py`
- Depends on: U-web-settings-03
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given a complete valid configuration, When checked, Then no error (type: happy; level: unit).
  2. Given an empty username, When the app is created, Then `ConfigurationError` names `username`; the same with `ENV=test` (AC-4) (type: error; level: api).
  3. Given a missing e-mail address, `not-an-address` and `a@b@c`, When checked, Then each is refused naming `email_address` (AC-4, W-1) (type: error; level: unit).
  4. Given a missing SMTP host, port, user or password, When checked, Then each is refused naming the field (AC-4, W-16) (type: error; level: unit).
  5. Given `smtp_starttls` false or implicit TLS without STARTTLS, When checked, Then refused (AC-4, W-14) (type: security; level: unit).
  6. Given a code-hash key of 31 bytes, one of 32 bytes, and two keys that are equal (code-hash, CSRF, username-hash pairwise), When checked, Then 31 and equal are refused, 32 passes (AC-4, W-1) (type: security; level: unit).
  7. Given a public origin that is not `https`, When checked, Then refused (AC-18) (type: security; level: unit).
  8. Given a refused start with canary values in the secret fields, When logs and the exception text are captured, Then no canary value appears, only field names (W-15) (type: security; level: api).
  9. Given the limit settings, When read, Then each default equals the spec value (30, 8192, 600, 60, 5, 5, 1800, 43200) and tests can lower them (C-4) (type: happy; level: unit).
  10. Given `pyproject.toml`, When read, Then `--cov-fail-under=90` is in the pytest options and the `backend` CI job runs `uv run pytest` (type: happy; level: ci).
