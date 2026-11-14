---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-11: Telegram intake (long polling)

- Layer: backend (adapter)
- Contract: `TelegramInbox` yields `Command` objects (button press, reply text) from updates; drops everything else.
- Files: `app/adapters/telegram_inbox.py`, `tests/adapters/test_telegram_inbox.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-telegram
- Criteria:
  1. Given an update from Marco's user and chat id, When received, Then a `Command` is produced (happy).
  2. Given an update from any other user or chat, When received, Then it is dropped without a reply and without effect (security; AC-11, AC-15).
  3. Given an update with an unknown shape (edited message, channel post, group), When received, Then it is dropped (security).
  4. Given a long-polling failure, When it occurs, Then it retries with backoff and keeps the offset so no update is lost or repeated (error).
  5. Given the bot token, When a request or error is logged, Then the URL is redacted (security; AC-24).
