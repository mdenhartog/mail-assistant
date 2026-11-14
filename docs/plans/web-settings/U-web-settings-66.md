---
intent: INT-002
feature: web-settings
---

# U-web-settings-66: Chart: environment cannot be overridden, digests everywhere (R1; challenge round 2; RT2-08, SEC2-05)

- Layer: infra
- Contract: the app chart renders `APP_ENVIRONMENT` from `.Values.environment` and fails when `api.env` or `web.env` sets `APP_ENVIRONMENT`, `APP_DATABASE_*`, `APP_TRUSTED_PROXY_*` or any limit key (`APP_*_PER_*`, `APP_CODES_PER_HOUR`, `APP_MAX_ATTEMPTS`); the agent Dockerfile and the Caddy image are pinned by `@sha256`; the worker chart gets a values schema that requires a digest when `environment` is production; the digest lint covers every Dockerfile and compose image in the repo.
- Files: `deploy/charts/app/templates/workloads.yaml`, `deploy/charts/app/values.schema.json`, `deploy/charts/worker/values.schema.json`, `deploy/charts/worker/values.yaml`, `agents/mail-triage/Dockerfile`, `compose.yaml`, `agents/mail-triage/tests/infra/test_ingress_gates.py`
- Depends on: U-web-settings-57, U-web-settings-58
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-docker, guardrail-kubernetes, guardrail-compose
- Criteria:
  1. Given environment production and `api.env.APP_ENVIRONMENT=development` or `APP_CODES_PER_HOUR=1000`, When `helm template` runs, Then it fails naming the key (type: security; level: chart).
  2. Given worker values with environment production and no digest, When the schema runs, Then it refuses (type: security; level: chart).
  3. Given every Dockerfile and compose image in the repo, When linted, Then each has `@sha256` or an explicit documented exception (type: security; level: unit).
