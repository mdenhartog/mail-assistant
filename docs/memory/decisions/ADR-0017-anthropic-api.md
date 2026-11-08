---
id: ADR-0017
title: "Models through the Anthropic API, not Amazon Bedrock"
status: accepted
area: agent-platform
tags: [llm, anthropic, bedrock, secrets]
date: 2026-11-08
guardrails: [guardrail-llm]
amends: ADR-0005
---

## Context

ADR-0005 chose the self-hosted agent platform and stated that models run through Amazon Bedrock unless `build_model` is changed. Marco does not use AWS for this project and will provide an Anthropic API key (INT-001, feature `mail-triage`, decision D8).

## Decision

- Agents call Claude through the **Anthropic API** (Anthropic's own cloud), not through Amazon Bedrock.
- Model routing from ADR-0014 stays: a small model first, escalation to a larger one when unsure. Model ids come from configuration, never from literals in code.
- The API key is a secret: supplied through `.env` locally (git-ignored) and a Kubernetes secret in production. It is never in code, images, logs or URLs.
- Before the first run Marco checks the data-retention setting of his Anthropic account and chooses zero retention if the account offers it.

## Consequences

- ADR-0005 stays valid for everything else (separate containers, Docker Desktop and Kubernetes). Only its model-provider sentence is replaced by this ADR.
- New agents use the Anthropic SDK. The existing `agents/assistant` scaffold still uses Bedrock; it is not used by `mail-triage` and is decided on separately.
- Mail content leaves our infrastructure for Anthropic: accepted risk A-1 in ADR-0018.
- No AWS credentials are needed for this feature.

## Alternatives

- Amazon Bedrock — rejected: Marco has no AWS setup and does not want it for this project.
- Local model (Ollama) — rejected earlier in ADR-0014: operational overhead without a privacy requirement that justifies it.
