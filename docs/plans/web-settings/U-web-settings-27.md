---
intent: INT-002
feature: web-settings
---

# U-web-settings-27: Notice buttons: Undo, Undo and lock, /web_unlock (R1; release gate)

- Layer: agent
- Contract: the callbacks `webundo:<token>` and `weblock:<token>` handled through the router: Undo restores the values as they were before the first web change the agent had not yet announced, guarded by the current version, with one audit record (via the agent role); "Undo and lock" first writes `web_auth.web_lock`, then undoes; the Telegram command `/web_unlock` (D-3) clears the lock; only the allowed user and chat.
- Files: `agents/mail-triage/app/usecases/web_notice_actions.py`, `agents/mail-triage/app/db/pg_web_lock.py`, `agents/mail-triage/app/usecases/dispatch.py`, `agents/mail-triage/app/core/settings_text.py`, `agents/mail-triage/tests/db/test_web_notice_actions.py`
- Depends on: U-web-settings-26
- Parallel: no
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given web changes 3, 4, 5 announced in three notices, When Undo of notice 5 is tapped, Then the values from before change 3 are restored with one audit record (AC-13, W-11) (type: happy; level: agent).
  2. Given the same burst, When Undo of notice 3 is tapped, Then the same result (AC-13) (type: edge; level: agent).
  3. Given Telegram changed the row after the burst, When Undo is tapped, Then nothing changes and the bot says it changed in the meantime (AC-13) (type: edge; level: agent).
  4. Given "Undo and lock", When tapped and the undo conflicts, Then `web_lock` is set anyway (AC-27, W-11) (type: security; level: db).
  5. Given "Undo and lock" tapped twice, When handled, Then one lock row and one undo (type: edge; level: db).
  6. Given `/web_unlock` from the allowed user, When sent, Then `web_lock` is cleared; from anyone else nothing happens and nothing is answered (AC-27) (type: security; level: agent).
  7. Given an expired or already used token, When tapped, Then the message is edited to "Expired" or "Already done" and nothing is written (type: edge; level: agent).
  8. Given a tap from another chat or user with a valid token, When handled, Then ignored (type: security; level: agent).
  9. Given the real agent role `mail_triage_runtime`, When the lock write and the undo run, Then both work with the grants of U-07 and no other `web_auth` table is touched (ADR-0033) (type: security; level: db).
  10. Given a failure path with canary zone and token, When logs are captured, Then no canary appears; and the new modules pass the same AST rule as U-26 (type: security; level: agent).
