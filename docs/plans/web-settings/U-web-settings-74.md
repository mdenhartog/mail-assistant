---
intent: INT-002
feature: web-settings
---

# U-web-settings-74: Production prepared, not deployed (R1; no rollout; D-21)

- Layer: infra
- Contract: everything for a production release exists but nothing is applied: `deploy/envs/production/values.yaml` and `deploy/envs/production/mail-triage.yaml` with the environment `production`, the trusted proxy settings, the HSTS and TLS mechanism of the chosen ingress controller (decision D-21, an ADR before this unit starts), `certAlert.enabled`, and every value Marco must supply marked `# REQUIRED` with a name (image digests, ingress host, the certificate issuer, the SMTP host and port, the sealed secrets); the controller's native objects for HSTS (no `includeSubDomains`, no preload), the HTTP to HTTPS redirect, the TLS minimum 1.2 and the 8 KB body cap rendered by the chart; an Argo CD `Application` manifest under `deploy/argocd/` that is not applied by anything in CI; and a test that renders the production values with the REQUIRED values supplied (`--set`) and refuses to render without any one of them. `docs/release/web-settings-prod.md` gets the exact commands and the staging probe of the checklist. Nothing is deployed and no production approval is implied.
- Files: `deploy/envs/production/values.yaml`, `deploy/envs/production/mail-triage.yaml`, `deploy/charts/app/templates/ingress.yaml`, `deploy/charts/app/values.schema.json`, `deploy/argocd/application.yaml`, `docs/release/web-settings-prod.md`, `agents/mail-triage/tests/infra/test_production_ready.py`, `deploy/charts/app/values.yaml`, `deploy/envs/local/values.yaml`, `deploy/charts/*/templates/_helpers.tpl`, `.github/workflows/ci.yml` (CRD schema location for kubeconform), the ingress tests of U-40, U-41 and U-57
- Built as (2026-11-14, ADR-0040): the ingress part of the app chart is rebuilt for Traefik with `ingress.controller: traefik` required (schema enum), a `Middleware` for HSTS (only `stsSeconds`), a `Middleware` for the 8 KB cap, a `redirectScheme` `Middleware` on a second Ingress at the `web` entry point and a `TLSOption` `VersionTLS12`; the ingress-nginx annotation vocabulary, `hstsAnnotation` and `controllerConfig` are gone. Production values hold the sentinel `REQUIRED` for every value Marco supplies; the Argo CD file has an AppProject and one Application per chart with manual sync.
- Depends on: U-web-settings-57, U-web-settings-66, U-web-settings-70
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-tls-certificates, guardrail-compose
- Criteria:
  1. Given the production values with every REQUIRED value supplied, When rendered, Then the chart passes the schema and the gates of U-57, U-66 and U-70 (digests, certificate alert, trusted proxies, forbidden keys) (type: happy; level: chart).
  2. Given the production values, When any one REQUIRED value is missing, Then the render fails naming it (type: error; level: chart).
  3. Given the rendered ingress objects, When searched, Then HSTS without `includeSubDomains` and preload, an HTTP to HTTPS redirect, the TLS minimum 1.2 and the 8 KB body cap are present for the chosen controller (AC-18, W-9) (type: security; level: chart).
  4. Given the repository, When searched, Then no workflow applies the Argo CD manifest or the production values (type: security; level: unit).
