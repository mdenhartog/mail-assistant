---
paths:
  - "deploy/**"
  - "**/Dockerfile"
  - "compose.yaml"
  - ".github/workflows/**"
---

# Infra rules (loaded only when working on deploy, Dockerfiles, compose or CI)

- Load guardrail-docker, guardrail-compose, guardrail-kubernetes, guardrail-helm and guardrail-tls-certificates where applicable.
- The check first (hadolint, Trivy, kubeconform, kube-linter, checkov, helm test), then the config.
- No secrets in Git; production only through a GitOps PR after explicit approval.
