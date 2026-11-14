---
intent: INT-002
feature: web-settings
---

# U-web-settings-58: TLS with verify-full for the agent and the migrate job (R1; challenge fix; SEC-10)

- Layer: infra, agent
- Contract: the agent runtime and the migrate job connect with `sslmode=verify-full` and the CA; `pg_hba.conf` uses `hostssl` for every role in the prod-like stack; the worker chart carries the CA and the setting.
- Files: `agents/mail-triage/app/settings.py`, `agents/mail-triage/app/db/engine.py`, `deploy/charts/worker/`, `deploy/prod-like/pg_hba.conf`, `compose.yaml`, `agents/mail-triage/tests/infra/`
- Depends on: U-web-settings-39
- Parallel: yes
- Guardrails: guardrail-tls-certificates, guardrail-helm, guardrail-compose, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the agent role connecting without TLS in the prod-like stack, When it tries, Then the server refuses (W-8, W-9) (type: security; level: prod-like).
  2. Given the worker chart, When rendered, Then the CA and `verify-full` are set for the runtime and the migrate job (type: security; level: chart).
  3. Given the agent settings in production, When `sslmode` is weaker than `verify-full`, Then start-up refuses (type: error; level: unit).
