---
intent: INT-008
feature: label-structure
---

# U-label-structure-14: Audit, success report and cross-cutting tests (R1)

- Component: mail-triage
- Layer: backend
- Contract: the list audit function `categories.list_json` records, besides id, name, description and position, each category's `kind`, `notify` and senders and the list's general instructions (found while building unit 11: today a change of a tick or a sender leaves no trace in `list_audit`; a migration `0028` replaces the function (0026 is the alert causes of unit 10, 0027 the skip counts of unit 36), the downgrade restores it; the api and the Telegram change notice keep working); audit records for sender-rule filings (matched entry stays in the agent-owned filing record under its retention); the daily AC-46 report adds the success numbers (share filed by a sender rule, model calls per day, always-notify alerts per day, share under "Other", Move-back rate of system-approved items); cross-cutting tests: canary strings in all sinks, 100 by 100 matching load, concurrency with two sessions and explicit barriers.
- Files: `agents/mail-triage/app/usecases/report.py`, `agents/mail-triage/app/core/audit.py`, tests in `agents/mail-triage/tests/` (security, load and concurrency suites)
- Depends on: U-label-structure-08, U-label-structure-09, U-label-structure-10
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-telegram
- Criteria:
  1. Given any sender-rule filing, upload-driven list change or system approval, When it happens, Then an audit record names the source with a keyed-digest actor and no mail text. (type: happy)
  2. Given the daily report, When it runs, Then it shows the five numbers of D22. (type: happy)
  3. Given canary strings in descriptions, senders, instructions and an incoming From that matches no rule, When mail is processed, Then they are not found in the log, access log, Sentry stub, Telegram stub or audit rows. (type: security)
  4. Given a mail arriving during an upload confirm, or an archive rename while mail is filed (two sessions, barriers), When both run, Then the mail uses either the old or the new list version, never a mix, and its filing record names the version. (type: edge)
  5. Given 100 categories with 100 senders each, When mail is matched, Then matching stays within the time bound. (type: edge)
