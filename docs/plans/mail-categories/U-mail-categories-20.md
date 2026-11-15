---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-20: Ingress route for the list save

- Component: platform
- Layer: infra
- Release: R1
- Contract: the Helm chart gives `PUT /api/categories` its own Traefik route with a buffering middleware of 32 KB (`maxRequestBodyBytes: 32768`); every other route keeps the 8 KB cap of ADR-0034 (W-9). The api enforces the same two limits itself (U-04). Decided by the user on 2026-11-15: a separate route, not a higher global cap, so the other routes keep the smaller limit.
- Files: deploy/charts/app/templates/ingress.yaml, deploy/charts/app/values.yaml, deploy/charts/app/README.md, deploy/charts/app/tests/*
- Depends on: U-mail-categories-04
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-tls-certificates
- Criteria:
  1. Given the rendered chart, Then a route for `PUT /api/categories` uses a buffering middleware with 32768 bytes and the route for every other path keeps 8192 (MC-12) (type: security)
  2. Given the rendered chart, Then `POST /api/categories`, the trailing-slash variant and any other `/api` path are matched by the 8 KB route (type: security)
  3. Given the rendered chart, Then the new route keeps the redirect, HSTS and TLS-minimum middlewares of the existing route (ADR-0040) (type: security)
  4. Given `helm lint` and `kubeconform`, Then both pass; the values schema rejects a body cap below 1 (type: error)
  5. Given the chart README, Then it names both limits and the reason (type: happy)
