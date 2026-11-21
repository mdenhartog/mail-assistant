---
intent: INT-008
feature: label-structure
---

# U-label-structure-31: Relax the category check constraints to the v2 limits

- Component: mail-triage
- Layer: backend
- Contract: one Alembic revision in the agent's chain (ADR-0025, ADR-0053) after `0022_plan_moved_count`: `ck_category_name_length` becomes 1 to 215 characters (the label `Assistant/` plus the name is at most 225), `ck_category_description_length` becomes at most 1 500, `ck_category_position` becomes 0 to 99 (100 categories); the SQLAlchemy models in `app/db/models.py` carry the same checks; the downgrade restores the v1 limits and refuses to run (a clear error, no data change) while a row exceeds them. Found while building unit 29: without it the api accepts a v2-valid list that PostgreSQL then refuses, and `categories_repo` turns that into a misleading 409. This unit lands in the same pull request as units 02, 28, 29 and 30.
- Files: `agents/mail-triage/migrations/versions/0023_category_v2_limits.py`, `agents/mail-triage/app/db/models.py`, tests in `agents/mail-triage/tests/db/`
- Depends on: U-label-structure-02
- Parallel: yes
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the migration ran, When a category with a 215-character name, a 1 500-character description and position 99 is inserted, Then PostgreSQL accepts it. (type: happy)
  2. Given the migration ran, When a name of 216 characters or an empty name, a description of 1 501 characters, or position 100 or -1 is inserted, Then PostgreSQL refuses it with a check violation. (type: error)
  3. Given existing categories within the v1 limits, When the migration runs, Then they are unchanged and it is idempotent (running the chain to head twice is safe). (type: edge)
  4. Given the downgrade and rows within the v1 limits, When it runs, Then the v1 checks are back; Given a row beyond them, Then the downgrade stops with a clear error and changes nothing. (type: edge)
  5. Given the models, When the schema is compared with the migrations, Then the checks match (no drift). (type: edge)
