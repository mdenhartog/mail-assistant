---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-16: Daily overview

- Layer: backend (use case)
- Contract: `send_overview()` at the configured time.
- Files: `app/usecases/overview.py`, `tests/usecases/test_overview.py`
- Depends on: U-03, U-09, U-11, U-12
- Parallel: yes (after those)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given mails filed today without alert, When the overview time arrives, Then one message gives counts per category and lists the mails with low confidence (happy; AC-31).
  2. Given nothing was filed, When the time arrives, Then no message is sent (edge; AC-31).
  3. Given the overview was already sent today, When run again, Then nothing is sent (edge).
  4. Given the overview time were to fall inside quiet hours, When it arrives, Then it is sent when quiet hours end (edge; guards a future change, see INT-002).
