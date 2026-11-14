---
intent: INT-002
feature: web-settings
---

# U-web-settings-40: Chart: local ingress, TLS and exposed paths (R1)

- Layer: infra
- Contract: the `app` chart ingress is local only (ADR-0037): no public host in any values file, a private address and a local host name from per-environment values; routes exactly `/api` and `/auth` to `api` and `/` to `web`; HTTP to HTTPS redirect; TLS 1.2 minimum; a certificate from a private CA through the issuer in values; `ingress.hsts` actually used (`max-age=31536000`, no `includeSubDomains`, no `preload`). Controller-specific parts (8 KB body cap, TLS minimum, log format with `$uri`) come from per-environment values (hosting is an open point).
- Files: `deploy/charts/app/templates/ingress.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/envs/local/values.yaml`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-kubernetes, guardrail-helm, guardrail-tls-certificates
- Criteria:
  1. Given the rendered ingress, When read, Then paths are exactly `/api` and `/auth` to the api service and `/` to web, and no rule routes `/docs`, `/openapi.json`, `/healthz`, `/readyz` or `/metrics` (AC-19, W-6) (type: security; level: chart).
  2. Given the rendered ingress with `tls.enabled`, When read, Then a `tls` block with the host and secret, an HTTP to HTTPS redirect, the issuer annotation from values and the HSTS setting from `ingress.hsts` without `includeSubDomains` and `preload` (AC-18, W-9) (type: security; level: chart).
  3. Given a values file with `tls.enabled: false`, `hsts: false`, or a host that is a public-looking name outside the configured local suffix, When `helm lint --strict` runs, Then it fails (AC-18, W-17) (type: error; level: chart).
  4. Given the local environment values (kind), When rendered, Then the 8 KB body cap, TLS 1.2 minimum and a log format without the query string are set through values; the chart default has no controller-specific annotation (AC-16, W-9) (type: security; level: chart).
  5. Given any values file in `deploy/`, When searched, Then there is no `LoadBalancer` service for api or web, no `nodePort` and no `externalIPs` (ADR-0037, W-17) (type: security; level: chart).
  6. Given the rendered output, When checked with kubeconform and kube-linter, Then both pass (type: happy; level: chart).
