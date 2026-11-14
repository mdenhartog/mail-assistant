---
intent: INT-002
feature: web-settings
---

# U-web-settings-68: The lock counts only wrong codes against the owner's real requests; an expired request dies on its first post (R1; challenge round 3; ADR-0039 amendment 2; RT3-01, RT3-04, SEC3-01)

- Layer: backend
- Contract: `check()` in `login_requests.py` knows the owner key (`username_key` of the configured username); a well-formed wrong, expired or exhausting code counts as `code_refused` only against a row whose `username_key` equals the owner key; a guess against a decoy row is recorded as `code_invalid`; when `check()` meets an expired row it sets `dead_at` in the same locked transaction and returns `Dead(existing=True)` only that first time, later posts get `Dead()`. The answers to the visitor stay identical for real and decoy rows (AC-30).
- Files: `backend/app/auth/login_requests.py`, `backend/app/auth/verify_code.py`, `backend/app/auth/event_rules.py`, `backend/tests/auth/test_verify_code.py`, `backend/tests/auth/test_login_requests.py`, `backend/tests/db/test_security_events.py`, `agents/mail-triage/tests/db/test_wrong_code_lock.py`
- Depends on: U-web-settings-63, U-web-settings-67
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given no request for the configured username, When one client asks codes for three unknown names and posts 5 well-formed wrong codes with each cookie, Then the sum of `code_refused` is 0, `code_invalid` holds them and the agent does not set the lock (W-13, R-3) (type: security; level: db).
  2. Given the owner's live request, When 5 wrong codes are posted, Then the sum of `code_refused` is 5 (type: happy; level: db).
  3. Given a request 11 minutes old, When 10 well-formed codes are posted with its cookie, Then `code_refused` is 1 and the other nine are `code_invalid` (type: security; level: db).
  4. Given a decoy and an owner request, When wrong codes are posted, Then status, body and `attemptsLeft` are the same shape (AC-30) (type: security; level: api).
