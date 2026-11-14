---
intent: INT-002
feature: web-settings
---

# U-web-settings-26: Web notices in the agent (R1; release gate)

- Layer: agent
- Contract: at each run `WebNotice.run(now)` selects `settings_change` records whose `db_role` is not the agent role and whose version (as an integer) is above the cursor in `poll_state`, sends one Telegram notice per change (old and new values, change number, channel `web`, time; no username) with the buttons "Undo" and "Undo and lock web sign-in", records an own token per notice in the notice table (not the conversation row) through an injected token source, and advances the cursor. Delivery is at least once. Quiet hours never hold the notice.
- Files: `agents/mail-triage/app/usecases/web_notice.py`, `agents/mail-triage/app/db/pg_web_notice.py`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/app/core/settings_text.py`, `agents/mail-triage/tests/db/test_web_notice.py`
- Depends on: U-web-settings-06, U-web-settings-07
- Parallel: yes
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a web change to version 3, When the agent runs, Then exactly one notice with old values, new values, change number 3, channel web, time and both buttons (AC-13, W-11) (type: happy; level: agent).
  2. Given the notice was sent, When the agent runs again, Then no second notice (cursor advanced) (AC-13) (type: happy; level: agent).
  3. Given a change made through Telegram (agent role), When the agent runs, Then no web notice (AC-13) (type: edge; level: agent).
  4. Given web changes at versions 9, 10 and 11, When the agent runs, Then three notices in numeric order (10 after 9) (ADR-0033) (type: edge; level: agent).
  5. Given a failure injected between the send and the cursor update (a store fake that raises on `advance`), When the agent runs twice, Then the notice is sent twice (at least once), the cursor ends advanced and there is one token record per send; Given the outbox fails before the send, Then the cursor did not move and the notice is sent on the next run (AC-13) (type: error; level: agent).
  6. Given a pending Telegram dialogue (the conversation row), When a web notice is sent, Then the conversation row and its message are unchanged (AC-13, ADR-0033) (type: edge; level: agent).
  7. Given a `FakeClock` inside the quiet hours that the change itself just set, When the agent runs, Then the notice is sent (AC-13, ADR-0033) (type: edge; level: agent).
  8. Given a web row whose `updated_by` text claims the agent, When selected, Then the notice is still sent because selection uses the server-derived `db_role` (W-11) (type: security; level: db).
  9. Given the real agent role `mail_triage_runtime` (not the owner), When the use case writes the cursor and the token record, Then it works with the grants of U-07 (type: security; level: db).
  10. Given the new agent modules, When parsed with `ast`, Then they call none of `datetime.now`, `time.time`, `uuid4`, `random.*`, `secrets.*`; time and tokens are injected; and a failure path with canary zone and token leaves no canary in the logs (type: security; level: agent).
