---
id: ADR-0013
title: Observability: Sentry + Grafana, synthetic journeys daily
status: accepted
area: observability
tags: [sentry, grafana, monitoring, production-signals]
date: 2026-11-08
guardrails: []
---
## Context
After a release, the team needs to detect errors, track performance, and confirm that core user journeys are working.

## Decision
- **Error tracking**: Sentry (backend Python SDK + frontend browser SDK)
- **Metrics / dashboards**: Grafana (fed by Prometheus or Grafana Cloud)
- **Synthetic journeys**: Playwright-based smoke tests run daily against the production environment
- **Eval schedule**: continuous LLM evals (accuracy of AI suggestions, latency) run on a daily schedule

## Consequences
- Sentry DSN is a secret; never committed to the repository.
- Grafana dashboards are defined as code in `deploy/`.
- The `production-signals` skill is used to wire up phase 10 of each feature.

## Alternatives
- Datadog — rejected: cost and complexity not justified for current team size.
- No observability — rejected: unacceptable for a production system.
