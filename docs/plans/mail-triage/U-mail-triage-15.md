---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-15: Snooze and close commands

- Layer: backend (use case)
- Contract: `snooze(alert_id, hours | "tomorrow")`, `close(alert_id)`, `release_due()`.
- Files: `app/usecases/snooze.py`, `tests/usecases/test_snooze.py`
- Depends on: U-02, U-03, U-09, U-11
- Parallel: yes (after those)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given an alert, When Marco chooses "remind me later" and sends "3", Then the alert is `snoozed` with due now + 3 h and no alert is sent before then (happy; AC-9).
  2. Given "tomorrow", When chosen, Then the due time follows U-03 (happy; AC-9).
  3. Given the due time passes, When `release_due` runs, Then exactly one new alert is sent and the alert is `open` (happy; AC-9).
  4. Given invalid input for the hours, When sent, Then Marco is asked again and the state is unchanged (error).
  5. Given "no more reminders", When chosen, Then the alert is `closed` and the mail is never alerted again but keeps its category (happy; AC-10).
  6. Given a due time inside quiet hours, When released, Then the alert is `held` until quiet hours end (edge; AC-32).
