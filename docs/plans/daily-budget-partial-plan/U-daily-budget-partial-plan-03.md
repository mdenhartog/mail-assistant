---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-03: Migration (expand): plan parts, series columns, the notice record and column grants

- Component: mail-triage agent
- Layer: backend
- Contract: One Alembic revision after U-02 adds to `categories.plan`: `part_no` (default 1), `start_cursor` (an internalDate and message id mark), `announced_at`, `pause_reason` (CHECK on the fixed set `budget | pace | waiting_for_part | cursor_lost | expired | ended`), and `series_ended_at` with a reason; unique (request, kind, part_no) next to the existing one-open-plan index; a BEFORE INSERT trigger that copies `start_cursor` of part N+1 from the end of part N and refuses another value or number; a table `categories.notice_day` (mailbox, UTC day) for the one-message-a-day rule; the `api` web role loses table-level SELECT on `categories.plan` and gets column-level SELECT without `build_cursor` and `start_cursor`. `resort_request` stays insert-only (no UPDATE for the agent). The plan also gets `fail_count` and `fail_mark` (the attempts of the model on the mail at the current position, so the count survives a restart). "A series is unfinished" is defined once as the SQL function `categories.series_unfinished(mailbox)` (not ended, not at the cap, a plan exists or more mail waits); the existing `request_resort` function is rebuilt to call it and to refuse with a typed error, so the api only maps that error to 409 (U-11) and the agent has no second definition. A backfill gives plans from before the migration part 1 and converts an old message-id cursor into a mark that continues after that mail. Two-instance tests use two real connections and a barrier (testcontainers). The database refuses to move a plan to `applying` while `announced_at` is empty and `kind = 'auto'` has items (T-12).
- Files: `agents/mail-triage/app/db/versions/00NN_plan_parts.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/app/db/grants.sql`, tests under `agents/mail-triage/tests/db/`
- Depends on: U-daily-budget-partial-plan-02
- Parallel: no
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given part 1 ended at cursor C, When the agent inserts part 2 with another start cursor or number, Then the stored values are C and 2 (SAC-9). (type: security)
  2. Given the agent role, When it updates `resort_request`, Then it fails with 42501 (SAC-9). (type: security)
  3. Given the web role, When it selects `build_cursor` or `start_cursor`, Then it fails with 42501; when it selects the part, the totals and the pause reason, Then it succeeds (SAC-16). (type: security)
  4. Given a `pause_reason` outside the fixed set, When it is stored, Then the CHECK refuses it (SAC-16). (type: security)
  5. Given two instances, When both insert part N+1 of one kind, Then only one succeeds (SAC-3, AC 21). (type: security)
  6. Given existing plans from before the migration, When it runs, Then each has part 1 and no series end (AC 12). (type: edge)
  7. Given the migration, When it is upgraded and downgraded, Then both complete and the schema matches the models. (type: happy)
  8. Given an `auto` part with items and an empty `announced_at`, When anything moves it to `applying`, Then the database refuses (SAC-14, T-12). (type: security)
  9. Given an unfinished series, When `request_resort` is called, Then it refuses with a typed error and stores nothing; given an ended series (Cancel, cap or expired), Then it accepts a new request (SAC-11, AC 17). (type: security)
  10. Given an in-flight build with an old message-id cursor, When the migration runs, Then the build continues after that mail and no mail is judged twice. (type: edge)
