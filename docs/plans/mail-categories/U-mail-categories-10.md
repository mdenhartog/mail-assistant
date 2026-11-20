---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-10: AC-46 daily report

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: `usecases/refile_report.py`: compares the label recorded in `filing` with the mail's current label, writes the counts (re-filed by hand, in 'Other') to the log and an audit table; purge of `filing` after a year.
- Files: agents/mail-triage/app/usecases/refile_report.py, agents/mail-triage/tests/test_refile_report.py
- Depends on: U-mail-categories-05, U-mail-categories-06
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given filings and a fake Gmail where 3 of 100 mails changed label, When the report runs, Then it reports 3 % re-filed (AC-46) (type: happy)
  2. Given mail now in 'Other', Then the share in 'Other' is reported (type: happy)
  3. Given a deleted mail, Then it is not counted as re-filed (type: edge)
  4. Given the report output, Then it holds no sender or subject (AC-30) (type: security)
