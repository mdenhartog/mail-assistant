---
intent: INT-008
feature: label-structure
---

# U-label-structure-36: The agent records skipped sender rules (R1)

- Component: mail-triage
- Layer: backend
- Contract: when the `From` address of a mail matches a sender entry of the current list but the sender is not authenticated (`authenticated_from_domain` gives nothing, C-5), the mail goes to the model like any other and its filing row gets the source `sender_rule_not_applied` with the matched entry in `source_ref` (the check constraint of revision 0025 already allows the value; nothing writes it yet). The agent also keeps a small derived table `categories.sender_skip` (mailbox id, entry, skipped count, last skipped time) that it updates in the same transaction as the filing, so the api can show a per-entry count without reading the agent-owned filing table. Revision 0027 adds the table, grants `SELECT` on it to the web role and `INSERT, UPDATE, DELETE` to the agent role, and a retention step that drops rows with no skip in the last 90 days; the downgrade drops the table. An entry removed from the list keeps its count until retention removes it, and the api shows only entries of the current list. No sender address or mail text goes into the table (the entry is a list value the user typed).
- Files: `agents/mail-triage/app/core/sender_rules.py`, `agents/mail-triage/app/usecases/triage.py`, `agents/mail-triage/app/db/pg_store.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/migrations/versions/0027_sender_skip.py`, tests
- Depends on: U-label-structure-08, U-label-structure-10
- Parallel: no
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a mail whose `From` matches a listed entry and whose sender is not authenticated, When it is processed, Then the model judges it, the filing source is `sender_rule_not_applied` with the entry as `source_ref` and the entry's skipped count is one higher. (type: happy)
  2. Given an authenticated mail from a listed sender, When it is processed, Then the source is `sender_rule` and no count changes. (type: edge)
  3. Given a mail from a sender that matches no entry, When it is processed, Then no count changes and the source is `model`. (type: edge)
  4. Given the same mail completed twice (a restart), When counted, Then the entry is counted once. (type: edge)
  5. Given the web role, When it reads `categories.sender_skip`, Then it can; When it writes, Then Postgres refuses; and a row older than 90 days is removed by the retention step. (type: security)
  6. Given revision 0027, When upgraded, downgraded and upgraded again, Then no drift is reported. (type: edge)
