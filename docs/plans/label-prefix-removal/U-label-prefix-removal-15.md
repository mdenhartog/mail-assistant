---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-15: Migration 0031 (contract): drop category_label, gmail_label and adoptable

- Component: mail-triage agent
- Layer: backend
- Contract: Released only after the rename is `done` in production: drops `category_label`, `gmail_label` and the `adoptable` code path, with a downgrade that restores the empty structures.
- Files: `agents/mail-triage/migrations/versions/0031_label_boundary_contract.py`, `agents/mail-triage/app/db/models.py`, `packages/category-policy/category_policy/policy.py`, tests under `agents/mail-triage/tests/db/`
- Depends on: U-label-prefix-removal-14
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given `label_migration` is `done`, When 0031 runs, Then the old tables are dropped and nothing reads them. (type: happy)
  2. Given `label_migration` is not `done`, When 0031 runs, Then it refuses. (type: error)
  3. Given 0031, When downgraded and run again, Then the result is the same. (type: edge)
  4. Given the source, When searched, Then `adoptable` and `gmail_label` appear nowhere. (type: edge)
