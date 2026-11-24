---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-06: Rename plan runner: build, rename, merge, skip, restore, notice

- Component: mail-triage agent
- Layer: backend
- Contract: A use case builds the plan from the `Assistant/` labels (`label_rename_item`: id, old name, new name, mail count, action rename or merge), waits for the confirmation row, runs each item by id (re-reading it first), merges into an existing label by adding it to the mails and removing the old one, restores from the backup, and sends one Telegram notice with counts.
- Files: `agents/mail-triage/app/usecases/label_rename.py`, `agents/mail-triage/app/db/pg_label_rename.py`, `agents/mail-triage/app/core/rename_plan.py`, tests under `agents/mail-triage/tests/`
- Depends on: U-label-prefix-removal-05
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-python, guardrail-pytest
- Criteria:
  1. Given `Assistant/Aankopen/Marktplaats` with 12 mails, When the user confirmed, Then the label is `Aankopen/Marktplaats`, the 12 mails are still on it, and colour and visibility are kept (AC 4). (type: happy)
  2. Given no confirmation, When the runner runs, Then no label is renamed (AC 5). (type: security)
  3. Given `Assistant/Amerika` and an existing `Amerika`, When run, Then the mails of the old label are on `Amerika`, the old label is removed from them, and a second run changes nothing (AC 20). (type: happy)
  4. Given a label renamed by hand after the preview, When run, Then the entry is skipped and reported (AC 26). (type: error)
  5. Given a completed rename, When Restore is requested, Then the old names return and the mail is intact (AC 27). (type: happy)
  6. Given an item the user skipped in the preview, When run, Then it is not touched. (type: edge)
  7. Given a crash after 3 of 10 items, When the runner restarts, Then it continues with the rest and `label_migration` becomes `done` only at the end. (type: edge)
  8. Given the notice and the logs, When written, Then they carry counts only (AC 18, 29). (type: security)
