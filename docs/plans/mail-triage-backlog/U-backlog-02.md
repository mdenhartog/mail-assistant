---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-02: Store methods for the catch-up

- Layer: backend (persistence)
- Contract: on `PgStore`: `catchup_state() -> CatchupState | None`, `start_catchup(at)` (idempotent: a second call keeps the first `started_at`), `finish_catchup(at)`, `complete_backlog(message_id, outcome)` (same as `complete` and sets `backlog = true`), `backlog_alerts() -> int` (alerts whose mail has `backlog = true`, any state).
- Files: `app/db/pg_store.py`, `tests/db/test_pg_store.py`
- Depends on: U-01
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given no row, When `catchup_state()` is read, Then it is `None` (type: happy).
  2. Given a started catch-up, When `start_catchup` is called again with a later time, Then `started_at` is unchanged (type: edge; AC-B4, AC-B5).
  3. Given a started catch-up, When `finish_catchup` runs, Then the state has `finished_at` and survives a new store instance (type: happy; AC-B5).
  4. Given a mail and an outcome with an alert, When `complete_backlog` runs, Then the mail has `backlog = true` and exactly one alert row exists (type: happy).
  5. Given two backlog alerts and one normal alert, When `backlog_alerts()` is read, Then it returns 2 (type: edge; AC-B10).
  6. Given `complete_backlog` is called twice for the same mail, When the second call runs, Then there is still one alert (type: error; AC-B5).
