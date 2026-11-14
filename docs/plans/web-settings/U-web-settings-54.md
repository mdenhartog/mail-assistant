---
intent: INT-002
feature: web-settings
---

# U-web-settings-54: Wrong codes are counted, the lock stops code mail, the mail text says what to do (R1; challenge fix; ADR-0039; RT-09, SEC-04, SEC-08, SEC-09)

- Layer: backend, database (migration 0011)
- Contract: `web_auth.security_event` gains `count`; a repeated `(kind, client_key, window)` increments it instead of being dropped; `client_key` is stored as a keyed digest; while the web lock is set, a code request answers as usual but creates no row and sends no mail; the code mail says that someone on the network knows the username if the code was not asked for and points to the Telegram Lock command.
- Files: `agents/mail-triage/migrations/versions/0011_security_event_count.py`, `backend/app/security_events.py`, `backend/app/auth/event_rules.py`, `backend/app/auth/request_code.py`, `backend/app/mail/message.py`, `backend/tests/db/test_security_events.py`, `backend/tests/auth/test_request_code.py`, `backend/tests/mail/test_message.py`
- Depends on: U-web-settings-53
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 5 wrong codes from one client in one minute, When recorded, Then one row with `count` 5 exists (W-13) (type: happy; level: db).
  2. Given a stored event, When read, Then `client_key` is a digest and no clear address is stored (type: security; level: db).
  3. Given the web lock is set, When a code is requested for the configured username, Then the answer is the same, no login request row is written and no mail is sent (AC-27) (type: security; level: api).
  4. Given the code mail, When rendered, Then it names the Lock command and contains no username or address of the sender (W-14, W-15) (type: security; level: unit).
