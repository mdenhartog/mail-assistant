---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-08: The plan store: parts, the lease and the series end

- Component: mail-triage agent
- Layer: backend
- Contract: `db/pg_resort.py` gains the part operations on the schema of U-03: `close_part` (the checked mails become one `auto` and one `review` plan with `part_no`), `next_part_start` (reads the end of the previous part), a build lease with a cursor compare-and-set in `record_progress`, `end_series(reason)` (idempotent, records the reason) and the plan view columns. Cancel, Undo, Lock, a web lock and a list change call `end_series`. `request_resort` refuses (a typed result, mapped to 409 by the api) while a series is unfinished.
- Files: `agents/mail-triage/app/db/pg_resort.py`, `agents/mail-triage/app/db/pg_web_lock.py`, `agents/mail-triage/app/usecases/move_back.py`, `agents/mail-triage/app/core/resort_plan.py`, tests under `agents/mail-triage/tests/db/` and `agents/mail-triage/tests/usecases/`
- Depends on: U-daily-budget-partial-plan-03, U-daily-budget-partial-plan-06
- Parallel: no
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a build that checked at least one mail, When the part closes, Then one `auto` and one `review` plan exist for the checked mails with the next part number (AC 2). (type: happy)
  2. Given a build that checked no mail, When the budget is empty, Then no part is closed and the plan waits (AC 3). (type: edge)
  3. Given two agent instances, When both run the build, Then each mail is judged at most once and only one part N+1 exists per kind (SAC-3). (type: security)
  4. Given Cancel, Undo or Lock on any part, When the next budget day starts, Then the series is ended and no further part is built or approved (SAC-13, AC 15). (type: security)
  5. Given a series that is unfinished, When `request_resort` is called, Then it is refused and nothing is stored (SAC-11, AC 17). (type: security)
  6. Given a list change during a series, When the build runs, Then the open parts are replaced and the series ends (AC 6). (type: edge)
  7. Given a series end, When the audit is written, Then it holds the plan uuid, the part number and a fixed reason only (SAC-17). (type: security)
