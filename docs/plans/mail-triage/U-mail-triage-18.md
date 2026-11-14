---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-18: Container and deployment

- Layer: infra
- Contract: Dockerfile, compose service, Helm values and network policy for `mail-triage`; secrets from environment or Kubernetes secrets.
- Files: `agents/mail-triage/Dockerfile`, `compose.yaml`, `deploy/charts/component/values-mail-triage.yaml`, `tests/infra/*`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-docker, guardrail-compose, guardrail-kubernetes, guardrail-helm
- Criteria:
  1. Given the image, When started, Then the process is non-root with a read-only root filesystem and no extra capabilities (security; AC-30).
  2. Given the chart values, When rendered and linted, Then a network policy allows only Gmail, Anthropic, Telegram and PostgreSQL, and no ingress exists (security; AC-30).
  3. Given the deployment, When rendered, Then replicas is 1 with a strategy that never runs two copies at once (edge; design).
  4. Given the rendered manifests and image, When scanned, Then they contain no secret value (security).
  5. Given the compose profile `dev`, When started, Then the service starts with a Postgres container and fake secrets from `.env` (happy).
