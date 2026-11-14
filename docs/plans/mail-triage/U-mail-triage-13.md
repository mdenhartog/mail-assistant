---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-13: Alert delivery

- Layer: backend (use case)
- Contract: `deliver_open_alerts()`: send each `open` alert once, honour the hourly cap, send held alerts after quiet hours.
- Files: `app/usecases/deliver_alerts.py`, `tests/usecases/test_deliver_alerts.py`
- Depends on: U-02, U-03, U-09, U-11, U-12
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given an `open` alert, When delivered, Then exactly one Telegram message is sent and its message id is stored (happy; AC-3).
  2. Given the same alert on the next run, When delivered, Then nothing is sent (edge; AC-5).
  3. Given held alerts and quiet hours end, When delivered, Then they go out together in one batch (happy; AC-32).
  4. Given more alerts than the hourly cap, When delivered, Then the excess is batched into one summary alert (edge; AC-26).
  5. Given Telegram fails, When delivering, Then the alert stays `open` and is retried without duplicate delivery (error; AC-12).
  6. Given each delivery, When done, Then an audit record is written without a body (security; AC-22).
