---
intent: INT-008
feature: label-structure
---

# U-label-structure-32: The filing code uses topic, extra label and source

- Component: mail-triage
- Layer: backend
- Contract: the agent code that reads or writes `categories.filing` (`pg_store`, `pg_categories`, `pg_list_sync`, `pg_refile`, `pg_resort`, `judgement` and their callers) switches from `filing.category_id` to `topic_id`, `extra_id` and `source` (always `model` for now) with `source_ref` empty; the AC-46 report and Undo and Move back keep working on `topic_id`; a migration `0025` drops `filing.category_id`, the bridge trigger and its function from unit 05 (the downgrade restores them and copies `topic_id` back). No behaviour changes: this is the expand-and-contract step that unit 05 prepared, split out of unit 08 so each unit stays small.
- Files: `agents/mail-triage/app/db/pg_store.py`, `agents/mail-triage/app/db/pg_categories.py`, `agents/mail-triage/app/db/pg_list_sync.py`, `agents/mail-triage/app/db/pg_refile.py`, `agents/mail-triage/app/db/pg_resort.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/app/core/judgement.py`, `agents/mail-triage/migrations/versions/0025_filing_topic.py`, tests in `agents/mail-triage/tests/`
- Depends on: U-label-structure-05
- Parallel: no
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a mail is filed, When the filing row is written, Then it carries `topic_id`, a null `extra_id`, `source` `model` and no `source_ref`; no code reads or writes `category_id`. (type: happy)
  2. Given the AC-46 report, an Undo and a Move back, When they run on rows written before and after the migration, Then they give the same results as before. (type: edge)
  3. Given migration `0025`, When it runs, Then `category_id`, the bridge trigger and its function are gone and every row keeps its `topic_id`; When the downgrade runs, Then they are back with `category_id` copied from `topic_id`; running the chain twice changes nothing. (type: edge)
  4. Given the grants matrix, When the agent role inserts into `filing`, Then the column grants name `topic_id`, `extra_id`, `source` and `source_ref`, and nothing refers to `category_id`. (type: security)
  5. Given the full agent suite, When it runs, Then it is green (the filing column set test of `test_judgement_store.py` lists the final columns). (type: happy)
