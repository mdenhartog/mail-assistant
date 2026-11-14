---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-03: Time policy (quiet hours, snooze, overview time)

- Layer: backend (pure core)
- Contract: `in_quiet_hours(now)`, `next_quiet_end(now)`, `snooze_due(now, hours | "tomorrow")`, `next_overview(now)`; the values (23:00-07:00, 18:00, 09:00, Europe/Amsterdam) are module constants (spec C7), not configuration.
- Files: `app/core/time_policy.py`, `tests/core/test_time_policy.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: —
- Criteria:
  1. Given 23:30 local, When asked, Then it is quiet hours and the end is 07:00 next day (happy; AC-32).
  2. Given 07:00 exactly, When asked, Then not quiet (edge).
  3. Given a daylight-saving change night, When computing the end of quiet hours, Then it is 07:00 local time (edge).
  4. Given "tomorrow" at 15:00, When snoozing, Then due is the next day at 09:00 local (happy; AC-9).
  5. Given a number of hours that is zero, negative or above 168, When snoozing, Then it is rejected (error).
  6. Given 17:59 and 18:00, When computing the next overview, Then 18:00 today and 18:00 tomorrow (edge; AC-31).
