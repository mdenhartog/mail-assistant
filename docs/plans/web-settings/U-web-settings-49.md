---
intent: INT-002
feature: web-settings
---

# U-web-settings-49: Audit retention purge in the migrate job (R1 since 2026-11-13)

- Layer: backend (database; agent image)
- Contract: `python -m app purge` runs under the owner role as a step of the migrate job, after migrate and grants (not a CronJob, not a runtime role): it deletes `settings.settings_change` rows older than one year and `web_auth.security_event` rows older than 90 days (Marco, 2026-11-13) (injected clock) and expired `login_request` and `session` rows. `settings_change` stays append-only for the runtime roles through grants; the owner purge is the one documented delete path. The migrate command runs the step, so the Job and the compose service need no change.
- Files: `agents/mail-triage/app/db/purge.py`, `agents/mail-triage/app/db/migrate.py`, `agents/mail-triage/app/__main__.py`, `agents/mail-triage/tests/db/test_purge.py`
- Depends on: U-web-settings-07, U-web-settings-08
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-python, guardrail-helm, guardrail-kubernetes
- Criteria:
  1. Given audit records 366 days and 364 days old (`FakeClock`), When the purge runs, Then only the older one is removed (AC-21) (type: happy; level: db).
  2. Given a record exactly 365 days old, When the purge runs, Then the boundary follows one stated rule, tested on both sides (AC-21) (type: edge; level: db).
  3. Given `security_event` rows older than 90 days, and expired `login_request` and `session` rows, When the purge runs, Then they are removed and live rows stay (AC-21, W-13) (type: happy; level: db).
  4. Given the agent role and the web role, When they delete from `settings_change` or truncate it, Then 42501 still (AC-17) (type: security; level: db).
  5. Given the migrate job, When it runs, Then the order is migrate, grants, purge, and a failing purge makes the job exit non-zero naming the step (AC-21) (type: error; level: db).
  6. Given the rendered worker chart, When searched, Then there is no `CronJob` and no workload with the owner secret other than the migrate Job (AC-21, W-13) (type: security; level: chart).
  7. Given the purge, When logs are captured, Then only the counts of removed rows are logged (type: security; level: db).
  8. Given the purge run twice, When repeated, Then the second removes nothing (type: edge; level: db).
