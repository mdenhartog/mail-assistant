---
intent: INT-002
feature: web-settings
---

# U-web-settings-70: Chart: case-insensitive env guards, pinned test image, a disruption budget that allows one eviction (R1; challenge round 3; RT3-06, RT3-08, SEC3-08)

- Layer: infra
- Contract: both charts compare env keys case-insensitively against every key the chart sets itself (plain and secret) and against the forbidden lists (worker: `ENVIRONMENT`, `DATABASE_*`; app: the U-66 list); the Helm test pod image is pinned by `@sha256` and the digest lint covers `deploy/charts/**/templates`; the api PodDisruptionBudget allows one disruption (`maxUnavailable: 1`), and the schema refuses `minAvailable >= api.replicas`.
- Files: `deploy/charts/app/templates/_helpers.tpl`, `deploy/charts/worker/templates/_helpers.tpl`, `deploy/charts/app/templates/tests/test-health.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `agents/mail-triage/tests/infra/`
- Depends on: U-web-settings-66
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-docker
- Criteria:
  1. Given `env.database_ssl: disable` on the worker or `api.env.app_public_origin` on the app, When `helm template` runs, Then it fails naming the key (type: security; level: chart).
  2. Given every image in `deploy/charts/**/templates`, When linted, Then each has `@sha256` (type: security; level: unit).
  3. Given production values, When rendered, Then the api PodDisruptionBudget allows one disruption; `minAvailable: 1` with one replica is refused by the schema (type: edge; level: chart).
