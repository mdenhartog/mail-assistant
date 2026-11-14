---
intent: INT-002
feature: web-settings
---

# U-web-settings-08: Migrate job creates the roles from a list; WEB_ROLE_PASSWORD everywhere (R1)

- Layer: infra (database)
- Contract: `migrate.py` creates the runtime roles from a list (the agent role and the web role) with the SCRAM, no-membership and no-replication rules of ADR-0030; `WEB_ROLE_PASSWORD` is a new required setting of the job. The same PR carries every consumer: the agent's `compose.yaml` migrate service, the CI `runtime-role` job's `.env` line, the worker chart's migration Secret key, Job env and README (sealing by standard input), so nothing on `main` goes red.
- Files: `agents/mail-triage/app/db/migrate.py`, `agents/mail-triage/app/settings.py`, `agents/mail-triage/compose.yaml`, `.github/workflows/ci.yml`, `deploy/charts/worker/templates/migration.yaml`, `deploy/charts/worker/README.md`, `agents/mail-triage/tests/db/test_migrate_job.py`
- Depends on: U-web-settings-07
- Parallel: no
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-compose, guardrail-helm, guardrail-kubernetes
- Criteria:
  1. Given the job with two roles and two passwords, When it runs, Then both roles exist with SCRAM verifiers computed client side, `NOREPLICATION NOBYPASSRLS`, no membership, and no statement the server received contains a clear password (ADR-0030) (type: security; level: db).
  2. Given a missing `WEB_ROLE_PASSWORD`, When the job runs, Then it exits non-zero naming the key, not a value, before any role is changed (type: error; level: db).
  3. Given the web role has a role membership or REPLICATION, When the job runs, Then REPLICATION is reset and the membership makes the job exit 6 naming the role (type: error; level: db).
  4. Given the job runs twice, When compared, Then the second run changes nothing (type: edge; level: db).
  5. Given `agents/mail-triage/compose.yaml`, When rendered with and without the variable, Then the migrate service passes `WEB_ROLE_PASSWORD` by reference and no literal value exists (type: security; level: ci).
  6. Given the CI `runtime-role` job, When read, Then its `.env` step writes `WEB_ROLE_PASSWORD` and the job still passes with the 19 forbidden statements of the agent role (type: happy; level: ci).
  7. Given the rendered worker chart, When read, Then the migration Secret has the `WEB_ROLE_PASSWORD` key, the Job env references it, a missing key fails the Job naming the key, and the README seals by standard input without `--from-literal=` (ADR-0029) (type: security; level: chart).
  8. Given the rendered Job and Secret, When searched, Then the web password is in no values file or ConfigMap (type: security; level: chart).
