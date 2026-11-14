---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-07: List notice, Undo and Telegram actions

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: `usecases/list_notice.py`: reads `list_audit` above the cursor, sends one notice per burst (old and new list, Undo; also in quiet hours), Undo writes the previous list as a new version through the same path; `telegram_action` nonces (hash, chat id, kind, target, expiry, single use); web lock respected.
- Files: agents/mail-triage/app/usecases/list_notice.py, agents/mail-triage/app/usecases/telegram_actions.py, agents/mail-triage/app/core/list_text.py, agents/mail-triage/tests/test_list_notice_*.py
- Depends on: U-mail-categories-06
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-telegram
- Criteria:
  1. Given a list change in the web app, When the agent runs, Then one Telegram notice with old and new list and Undo is sent, also in quiet hours (AC-31) (type: happy)
  2. Given several changes in a burst, Then one notice and the Undo restores the list from before the burst as a new version (AC-31, MC-14) (type: edge)
  3. Given Undo pressed twice, late, or by another chat, Then nothing changes and the answer says so (AC-48) (type: security)
  4. Given a name or description with Telegram markup or control characters, Then the text is sent as escaped plain text and never exceeds the message limit (AC-29) (type: security)
  5. Given the agent's own Undo, Then exactly one notice is produced (type: edge)
  6. Given any notice, Then it holds no sender or subject (canary check, AC-30) (type: security)
  7. Given a list change or Undo, Then an append-only audit record with channel and actor digest exists (AC-36) (type: happy)
