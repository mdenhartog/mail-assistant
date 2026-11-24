---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-05: list_sync rebuilt: no seed from Gmail, "Other" and archive by id, the migration gate

- Component: mail-triage agent
- Layer: backend
- Contract: `list_sync` no longer seeds version 1 from `Assistant/` labels; it resolves managed ids (creating or adopting by list name) for categories, "Other" and the archive, refreshes counts and the label names for the api, and makes no label write while `label_migration` is not `done`. It supplies the `LabelBook` that units 17 and 18 expect (`managed()`, `names()` cached per run, `other()`, `topic(category_id)`, `remember(label, label_id)`) from the `managed_label` table and the settings, and it updates the end-to-end tests that still build the old pipeline shapes (`tests/db/test_end_to_end.py`, `tests/db/test_catch_up_end_to_end.py`). It also wires the new adapter signatures (`GmailResort(service, managed)`, `GmailApply(service, managed)`, `GmailReader(..., managed=)`) in `wiring.py`, and passes `own_default` to `validate_label_setting_name` in `scope.usable_archive_name` (unit 16 added the fourth argument).
- Files: `agents/mail-triage/app/wiring.py`, `agents/mail-triage/app/core/scope.py`, `agents/mail-triage/app/usecases/list_sync.py`, `agents/mail-triage/app/db/pg_list_sync.py`, `agents/mail-triage/app/db/pg_store.py`, tests under `agents/mail-triage/tests/`
- Depends on: U-label-prefix-removal-02, U-label-prefix-removal-03, U-label-prefix-removal-04
- Parallel: no
- Guardrails: guardrail-gmail, guardrail-python, guardrail-pytest
- Criteria:
  1. Given a first start with no list, When the agent runs, Then it seeds nothing from Gmail and waits for the upload (AC 14). (type: edge)
  2. Given `label_migration` is `pending` or `confirmed`, When `list_sync` runs, Then it makes no label write at all (AC 25). (type: security)
  3. Given `label_migration` is `done` and a category is renamed in the list, When synced, Then its label is renamed by id. (type: happy)
  4. Given the default names on a new installation, When synced, Then "Other" and the archive label exist as `Other` and `Archive` (AC 12). (type: happy)
  5. Given the user changed the name of "Other", When synced, Then that label is renamed by id and the id is kept (AC 12). (type: happy)
  6. Given a name that equals an existing label of the user, When synced, Then it is adopted and syncing twice changes nothing (AC 19). (type: edge)
  7. Given the counts for the api, When refreshed, Then they are by managed id and contain no mail data. (type: happy)
