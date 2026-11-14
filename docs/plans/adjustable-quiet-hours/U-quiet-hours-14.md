---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-14: Wiring and end-to-end

- Layer: backend
- Contract: wiring of `PolicySource`, the stores, the conversation store and the router in `wiring.py`/`runner.py`; end-to-end tests with a real PostgreSQL and a fake Telegram port; golden-master run of the first-release suites.
- Files: `app/wiring.py`, `app/runner.py`, `app/settings.py`, `tests/db/test_settings_end_to_end.py`
- Depends on: U-quiet-hours-06b, U-quiet-hours-11, U-quiet-hours-12, U-quiet-hours-13
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the settings schema absent, and separately an empty table, When the full existing suites run, Then they pass unchanged (AC-1) (type: happy).
  2. Given a Telegram change of the time zone, When the next run happens, Then quiet hours, overview and the remind default use the new values (AC-22) (type: happy).
  3. Given the agent compose profile started without the backend service, When a Telegram change is made, Then it is applied in the next run (AC-35) (type: edge).
  4. Given the agent and the shared package, When the contract fixture runs, Then both agree on the schema (AC-36) (type: happy).
  5. Given a stranger's `/settings` and a stranger's old button, When sent end to end, Then no row is written and nothing is sent (AC-3) (type: security).
