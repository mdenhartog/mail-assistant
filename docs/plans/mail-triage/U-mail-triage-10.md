---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-10: Triage pipeline

- Layer: backend (use case)
- Contract: `run_once()`: list, claim, judge, file, create alert state; per-mail retry limit.
- Files: `app/usecases/triage.py`, `tests/usecases/test_triage.py`
- Depends on: U-02, U-03, U-04, U-05, U-08, U-09
- Parallel: no
- Guardrails: guardrail-python
- Criteria:
  1. Given a new non-urgent mail, When run, Then it is filed under one category, no alert is created and nothing is deleted (happy; AC-1, AC-2, AC-4).
  2. Given a new urgent mail outside quiet hours, When run, Then the alert state is `open` (happy; AC-3).
  3. Given a new urgent mail inside quiet hours, When run, Then it is filed at once and the alert is `held` (edge; AC-32).
  4. Given the same mail seen twice, When run twice, Then it is processed once (edge; AC-12).
  5. Given Gmail or the model is down, When run, Then no mail is lost or doubled and the next run resumes (error; AC-12).
  6. Given a mail that fails the retry limit, When run, Then the others continue and one error notice is requested (error; AC-27).
  7. Given a daily budget or alerts-per-hour cap, When exceeded, Then mails are still filed (edge; AC-26).
