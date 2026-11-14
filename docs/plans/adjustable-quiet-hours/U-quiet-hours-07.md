---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-07: Router registry, tokens and expiry

- Layer: backend
- Contract: `CommandRouter` dispatches to registered handlers (settings, snooze, reply); slash commands before awaited text; settings buttons `set:<key>:<nonce>`, `tz:<index>:<nonce>`, `cancel:<nonce>`, `undo:<nonce>`; replayed `update_id` ignored; expired questions edit their message.
- Files: `app/usecases/dispatch.py`, `app/adapters/telegram_inbox.py`, `app/adapters/telegram_outbox.py`, `tests/usecases/test_dispatch.py`, `tests/adapters/test_telegram_inbox.py`
- Depends on: U-quiet-hours-06a
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given a fake registered handler and a pending snooze question, When `/settings` and a change start, Then the old question is replaced, the bot says what was dropped, and later text is read only as the settings answer (AC-5) (type: edge).
  2. Given a button with an old nonce, or forwarded to another chat, When tapped, Then nothing changes and a fresh card is offered (AC-4) (type: security).
  3. Given a user or chat that is not allowed, When any command or button arrives, Then nothing is answered (AC-3) (type: security).
  4. Given a replayed Telegram update, When it arrives twice, Then it is handled once (type: security).
  5. Given Cancel, When tapped, Then the old value stays and no row is written (AC-7) (type: happy).
  6. Given a button tap, When handled, Then the callback is answered so no spinner remains (type: happy).
  7. Given an injected `FakeClock`, When the expiry table 14:59:59, 15:00:00, 15:00:01 runs, Then used, expired, expired; the old message is edited to "Expired" without buttons and "Start again" is offered (AC-6) (type: edge).
  8. Given text that arrives with no pending question after expiry, When handled, Then the usual "use the buttons" answer is given, never a settings answer (type: error).
  9. Given a pending settings question, When an old snooze button is tapped, Then the settings question stays intact (type: edge).
  10. Given a double tap, or a callback and a text at once, When handled, Then only one write happens (type: edge).
  11. Given a tap from another chat id with a valid nonce, When handled, Then it is ignored; the allowed-user and chat check stays in the Telegram intake and has its own test (AC-3, AC-4) (type: security).
  12. Given a failure path, When logs are captured, Then no token or zone value appears (AC-33) (type: security).
