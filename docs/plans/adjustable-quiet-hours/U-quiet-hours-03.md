---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-03: Rebuild time_policy on TimePolicy (core and callers, one PR)

- Layer: backend
- Contract: `in_quiet_hours`, `next_quiet_end`, `next_overview`, `remind_due` (the old `snooze_due` is renamed `remind_due(now, amount, policy)`) and `day_start` take a `TimePolicy` and compare UTC moments (ADR-0027). The module constants are removed. Two units on one branch: 03a the core functions and their tests; 03b the callers (`overview.py`, `deliver_alerts.py`, `snooze.py`, `triage.py`) pass `DEFAULT_POLICY` until U-12 and U-13 replace it.
- Files: 03a `app/core/time_policy.py`, `tests/core/test_time_policy.py`; 03b `app/usecases/overview.py`, `deliver_alerts.py`, `snooze.py`, `triage.py`, `tests/usecases/test_overview.py` (the `OVERVIEW_AT` monkeypatch becomes `replace(DEFAULT_POLICY, overview_at=...)`), `tests/usecases/test_snooze.py`
- Depends on: U-quiet-hours-01b
- Parallel: no
- Guardrails: guardrail-python
- Criteria:
  1. Given the existing time_policy tests with `DEFAULT_POLICY`, When run, Then they pass unchanged (AC-1) (type: happy).
  2. Given quiet hours 01:00-06:00, When asked at 23:30, 03:00, 06:00, Then not quiet, quiet, not quiet (AC-12) (type: edge).
  3. Given zone America/New_York with 23:00-07:00, When the moment is 23:30 New York time, Then quiet (AC-23) (type: happy).
  4. Given Europe/Amsterdam, America/New_York and one midnight-change zone on both clock-change days, When quiet hours, next quiet end, next overview and the remind due moment run for a time in the gap and a time that occurs twice, Then results follow ADR-0027 (AC-28) (type: edge).
  5. Given a 12 h window on a 23 h and a 25 h day, When validated and asked, Then both agree (AC-28) (type: edge).
  6. Given `now` exactly at the quiet start and the quiet end, When asked, Then quiet from the start, not quiet at the end (type: edge).
  7. Given a `now` without a time zone, When asked, Then an error (type: error).
  8. Given a `now` in a non-UTC zone, and one function called with two policies of different zones, When asked, Then results are correct (no `ZoneInfo` cache effect) (type: edge).
  9. Given Asia/Kolkata (UTC+5:30), Asia/Kathmandu (UTC+5:45) and Australia/Sydney (southern flip), When asked, Then results are correct (type: edge).
  10. Given a search of `app/` for `TIME_ZONE|QUIET_START|QUIET_END|OVERVIEW_AT|TOMORROW_AT`, When run, Then there is no hit outside the policy code (type: happy).
  11. Given mutation testing on `time_policy.py`, When run, Then the score is at least 85 % (type: security).
