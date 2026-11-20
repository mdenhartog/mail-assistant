---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-06: Label sync and the Archive label

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: Narrow adapter `adapters/gmail_resort.py` (list, read, add, remove, create, rename by id; no delete), `usecases/list_sync.py`: seed version 1 from current labels, create missing `Assistant/` labels and `Archive`, rename by id for name-only changes, refresh `category_count` and `gmail_label`, advance `list_cursor` after the Gmail effects.
- Files: agents/mail-triage/app/adapters/gmail_resort.py, agents/mail-triage/app/usecases/list_sync.py, agents/mail-triage/tests/test_list_sync_*.py, agents/mail-triage/tests/test_gmail_allowlist.py
- Depends on: U-mail-categories-01, U-mail-categories-03, U-mail-categories-05
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given a Gmail without `Archive` (or where it was deleted), When the agent starts, Then it exists afterwards, once, also with overlapping runs, and the agent never adds mail to it (AC-25) (type: happy)
  2. Given the first start, Then version 1 is seeded from the current labels and the api stops answering `not-ready` (AC-49) (type: happy)
  3. Given a name-only change, Then the Gmail label is renamed by id, no plan and no model call; a new name equal to an existing label was refused at save (AC-40) (type: happy)
  4. Given the adapter, When its public operations are listed (reflection), Then they equal the allow-list and none can delete a label, trash, spam, delete mail or send (AC-28) (type: security)
  5. Given a rename or change of `Archive`, a label outside `Assistant/` or a system label, Then it is refused (AC-28) (type: security)
  6. Given a crash after the Gmail effects and before the cursor moves, When the run repeats, Then the renames are idempotent by label id and nothing is done twice (type: error)
  7. Given an older label under `Assistant/` not on the list, Then it appears in `gmail_label` for the api and the mail keeps its label (AC-53) (type: edge)
