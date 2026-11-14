---
intent: INT-002
feature: web-settings
---

# U-web-settings-41: Chart: NetworkPolicy, one replica, secrets and SMTP egress (R1; release gate)

- Layer: infra
- Contract: ADR-0034, ADR-0029, design section "Deployment". `api.replicas` is 1 (schema maximum 1); `api` and `web` ingress NetworkPolicy accepts from one peer (namespace selector and pod selector in one `from` item) selecting the ingress controller; `api` egress to the database, DNS and the SMTP host and port from values only (no TCP 443 rule, no identity-provider egress); no `web-to-api` rule; the api reads database URL, code-hash key, CSRF key, username-hash key from the Secret `<release>-api` and the SMTP credential from a second Secret (both SealedSecrets created by the operator, README steps); username, address, SMTP host and port, public origin and notice interval are plain values. An optional certificate-expiry `PrometheusRule` 14 days ahead, off by default (D-7; a gate for production).
- Files: `deploy/charts/app/templates/networkpolicy.yaml`, `deploy/charts/app/templates/workloads.yaml`, `deploy/charts/app/templates/certalert.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/charts/app/README.md`
- Depends on: U-web-settings-08, U-web-settings-40
- Parallel: no
- Guardrails: guardrail-kubernetes, guardrail-helm, guardrail-tls-certificates
- Criteria:
  1. Given the rendered api Deployment, When read, Then `replicas: 1`; a values file with 2 fails the schema (ADR-0034, W-7) (type: security; level: chart).
  2. Given the rendered NetworkPolicy, When read, Then ingress to `api` and `web` has exactly one `from` item with a namespace selector and a pod selector together, and no empty selector (W-9, W-17) (type: security; level: chart).
  3. Given the render, When searched, Then there is no `web-to-api` rule and no policy that admits every namespace (W-17) (type: security; level: chart).
  4. Given the api egress, When read, Then only the database, DNS (UDP and TCP 53) and the SMTP host and port from values; no TCP 443 rule and no `0.0.0.0/0` (W-9, W-16) (type: security; level: chart).
  5. Given the api container env, When read, Then database URL, the three keys and the SMTP credential come from `secretKeyRef` and appear in no values file, ConfigMap or template literal (ADR-0029, W-16) (type: security; level: chart).
  6. Given the chart and the README, When searched for `sslmode=disable`, `verify-none`, `insecure` and `SSL_CERT_FILE`, Then no hit; the README documents the asyncpg `ssl` `verify-full` setting for the database URL (W-8, W-9) (type: security; level: chart).
  7. Given `certAlert.enabled=true`, When rendered, Then a `PrometheusRule` with a 14-day expiry condition; when false nothing is rendered (D-7, W-9) (type: happy; level: chart).
  8. Given the README, When checked, Then sealing uses standard input and no `--from-literal=` for secret keys, and the new keys are listed (ADR-0029) (type: security; level: chart).
  9. Given `helm lint --strict`, kubeconform and kube-linter for the `app` chart, When run, Then they pass (readiness `/readyz`, liveness `/healthz`, non-root, read-only root file system) (type: happy; level: chart).
