---
id: ADR-0012
title: Hosting: Kubernetes via Helm + Argo CD
status: accepted
area: hosting
tags: [kubernetes, helm, argocd, docker]
date: 2026-11-08
guardrails: [guardrail-kubernetes, guardrail-helm, guardrail-docker, guardrail-compose]
---
## Context
The application needs a production deployment target and a local development environment.

## Decision
- **Local**: `docker compose --profile dev up` (compose.yaml)
- **Production**: Kubernetes via Helm charts (`deploy/charts/`) + Argo CD GitOps
- **Registry**: GHCR (GitHub Container Registry), images signed with cosign keyless
- **Cluster details**: deferred — specified when the first deployment spec is written

## Consequences
- The `guardrail-kubernetes`, `guardrail-helm`, `guardrail-docker` and `guardrail-compose` guardrails apply to all infrastructure code.
- TLS certificates are managed by cert-manager (guardrail-tls-certificates).
- Cluster, namespace and cloud provider choices are recorded in a new ADR when first needed.

## Alternatives
- Serverless (Lambda, Cloud Run) — rejected: the agent platform (ADR-0005) requires persistent containers.
