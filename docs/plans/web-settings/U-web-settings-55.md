---
intent: INT-002
feature: web-settings
---

# U-web-settings-55: Agent sets the web lock after repeated wrong codes (R1; challenge fix; ADR-0039; RT-07, SEC-03)

- Layer: agent
- Contract: when the summed `count` of `code_refused` events reaches 15 in 24 hours, the agent sets the web lock once and sends a Telegram notice (count, time; no code, username or address); Marco unlocks with `/web_unlock`; U-48 is the notice at 5 in 10 minutes.
- Files: `agents/mail-triage/app/usecases/code_alert.py`, `agents/mail-triage/app/db/pg_web_lock.py`, `agents/mail-triage/app/db/pg_security_events.py`, `agents/mail-triage/app/usecases/web_notice_actions.py`, `agents/mail-triage/app/usecases/dispatch.py`, `agents/mail-triage/app/core/settings_text.py`, `agents/mail-triage/app/wiring.py`, `agents/mail-triage/tests/usecases/test_code_lock.py`, `agents/mail-triage/tests/db/test_wrong_code_lock.py`
- Depends on: U-web-settings-48, U-web-settings-54
- Parallel: no
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given 15 wrong codes in 24 hours (`FakeClock`), When the agent runs, Then the lock is set and one notice is sent (W-13) (type: happy; level: agent).
  2. Given 14, or 15 over 24 hours 1 second, When it runs, Then nothing changes (type: edge; level: agent).
  3. Given a set lock, When the agent runs again, Then no second notice and no second write (type: edge; level: agent).
  4. Given `/web_unlock`, When Marco sends it, Then sign-in works again and the old events do not set the lock again (type: edge; level: agent).
  5. Given the sign-in mail names `/web_lock` (`LOCK_COMMAND`), When Marco sends `/web_lock` from the allowed chat, Then the lock is set and the agent confirms it and how to unlock; setting it again changes nothing and says it was already locked; from another chat nothing happens and nothing is answered (AC-27) (type: security; level: agent).
  6. Given events that were counted before a lock, or arrived while it was set, When `/web_unlock` lifts the lock, Then they never count again: the rule is that every event with an id at or below the newest id seen at the moment the lock is set, or seen while it is set, is spent; only newer events count (state of the rule: in memory, so a restart while unlocked forgets it and stale events inside 24 hours may set the lock once more, fail-closed) (type: edge; level: agent).
  7. Given the lock notice and the logs, When captured with canary values, Then no digest, username, address or code appears, and the notice names the count, the time and `/web_unlock` (W-13, W-15) (type: security; level: agent).
  8. Given the real agent role, When the lock is set and read, Then `web_lock` works and `security_event` stays read-only (type: security; level: db).
