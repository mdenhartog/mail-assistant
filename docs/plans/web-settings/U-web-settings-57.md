---
intent: INT-002
feature: web-settings
---

# U-web-settings-57: Ingress gates: HSTS, certificate alert, image digests (R1; challenge fix; RT-10, SEC-05, SEC-07)

- Layer: infra
- Contract: `values.schema.json` requires a non-empty HSTS mechanism when `hsts` is true; chart tests assert HSTS, the HTTP redirect and the TLS minimum for every environment values file that sets an ingress class; `certAlert.enabled` and an image `digest` are required when the environment is production; the base images of both Dockerfiles are pinned by `@sha256`. The ingress controller itself stays open (D-7, plan open points).
- Files: `deploy/charts/app/values.schema.json`, `deploy/charts/app/values.yaml`, `deploy/charts/app/templates/ingress.yaml`, `backend/Dockerfile`, `apps/web/Dockerfile`, `deploy/charts/app/tests/`
- Depends on: U-web-settings-41
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-docker, guardrail-tls-certificates
- Criteria:
  1. Given `hsts: true` and an empty annotation key, When the schema runs, Then it refuses (AC-18) (type: error; level: chart).
  2. Given each environment values file, When rendered, Then an HSTS directive, an HTTP redirect and the minimum TLS version are present or the test names what is missing (AC-18) (type: security; level: chart).
  3. Given production values without `certAlert.enabled` or a digest, When the schema runs, Then it refuses (W-9) (type: security; level: chart).
  4. Given both Dockerfiles, When linted, Then every `FROM` has a digest (type: security; level: unit).
