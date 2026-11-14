---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-06: Overview lists old urgent mail

- Layer: backend
- Contract: `FiledMail` gets `urgent: bool`; `PgStore.filed_without_alert_since` fills it; `build_overview` adds the section "Old mail that looked urgent" (at most 10 lines, then "…and n more"), escaped and capped like the existing sections, only for mails filed without an alert and urgent. Counts per category are unchanged.
- Files: `app/usecases/overview.py`, `app/db/pg_store.py`, `tests/usecases/test_overview.py`, `tests/db/test_pg_store.py`
- Depends on: —
- Parallel: yes (U-02 also edits `pg_store.py`; merge in order U-02, U-06)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given urgent mails filed without an alert, When the overview is built, Then they appear in the new section with sender and subject (type: happy; AC-B10).
  2. Given no urgent mail without an alert, When the overview is built, Then the section is absent and the text equals today's text (type: edge).
  3. Given a subject with markup, When the section is built, Then it is escaped and capped (type: security; SC-7).
  4. Given more than 10 such mails, When the overview is built, Then 10 are listed, the rest is counted and the message stays within the Telegram limit (type: edge).
  5. Given the store, When `filed_without_alert_since` runs, Then `urgent` is true only for urgent mails (type: happy).
