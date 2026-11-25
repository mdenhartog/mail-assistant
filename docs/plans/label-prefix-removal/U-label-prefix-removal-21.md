---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-21: Database length limits follow the policy: 255 characters for labels

- Component: mail-triage agent
- Layer: backend
- Contract: Found while building unit 19: the policy allows label names up to 255 characters, but the `categories` tables still check `category.name` at most 215 and `list_settings.archive_label` at most 225 (and `other_label` at most 225 in migration 0030), so a valid name of 216 to 255 characters fails with a 500 on save. Migration 0030 is unreleased, so this unit edits it in place: the CHECK limits of `category.name`, `list_settings.archive_label`, `list_settings.other_label`, `managed_label.label_name`, `label_rename_item.old_name` and `new_name` and `deleted_label.name` become 255 characters (counted as characters, like the policy), with the model constants, the downgrade, and tests at 255 and 256.
- Files: `agents/mail-triage/migrations/versions/0030_label_boundary.py`, `agents/mail-triage/app/db/models.py`, tests under `agents/mail-triage/tests/db/`
- Depends on: U-label-prefix-removal-02
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest, guardrail-python
- Criteria:
  1. Given a category name of 255 characters, When it is stored, Then it is accepted; with 256 characters, Then the CHECK constraint refuses it. (type: edge)
  2. Given an Other or archive name of 255 and 256 characters, When stored, Then the same boundary holds. (type: edge)
  3. Given a multibyte name of 255 characters, When stored, Then it is accepted (the limit counts characters). (type: edge)
  4. Given the managed, rename and deleted-label tables, When a name of 255 characters is stored, Then it is accepted. (type: edge)
  5. Given 0030 run twice and downgraded, When checked, Then the limits are consistent and nothing else changes. (type: edge)
  6. Given the api saves a list with a 255 character name, When it runs against the real schema, Then it answers 200 and not 500 (AC 32). (type: happy)
