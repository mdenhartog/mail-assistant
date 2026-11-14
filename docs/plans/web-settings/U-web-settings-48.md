---
intent: INT-002
feature: web-settings
---

# U-web-settings-48: Telegram alert after 5 wrong or expired codes (R1 since ADR-0039)

- Layer: agent
- Contract: the agent role gains `SELECT` on `web_auth.security_event` (grants.sql); at each run it counts `code_refused` events in the last 10 minutes; at 5 or more it sends one notice (count, time; no code, no username), at most one per 10 minutes. Other kinds (`code_request_refused`, `rate_limited`, `csrf_refused`, `mail_failed`) never count and never alert.
- Files: `agents/mail-triage/app/usecases/code_alert.py`, `agents/mail-triage/app/db/pg_security_events.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/tests/db/test_code_alert.py`
- Depends on: U-web-settings-13, U-web-settings-26
- Parallel: yes
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given 5 `code_refused` events within 10 minutes (`FakeClock`), When the agent runs, Then one notice with the count and time and no code or username (AC-20 second half, W-13) (type: happy; level: agent).
  2. Given 4 events, and 5 events spread over 10 minutes 1 second, When the agent runs, Then no notice (AC-20) (type: edge; level: agent).
  3. Given 50 `rate_limited`, `csrf_refused` and `mail_failed` events, When the agent runs, Then no notice (AC-20) (type: security; level: agent).
  4. Given a notice was sent, When the agent runs again within 10 minutes with more events, Then no second notice; after 10 minutes a new one may follow (type: edge; level: agent).
  5. Given the real agent role, When it selects `security_event`, Then it works; when it inserts, updates or deletes there, or touches `session` or `login_request`, Then 42501 (type: security; level: db).
  6. Given logs and the notice text, When captured with canary values, Then no digest, username or code appears (W-13, W-15) (type: security; level: agent).
