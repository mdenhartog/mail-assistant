---
id: ADR-0014
title: "Model routing: automatic Haiku → Sonnet → Opus"
status: accepted
area: model-routing
tags: [llm, model-routing, claude]
date: 2026-11-08
guardrails: [guardrail-llm]
---
## Context

The agent and assistant components call Claude models. Routing determines which model tier handles which task.

## Decision

Automatic model routing is **on**:

- Light tasks (classification, intent detection, short summaries): **Claude Haiku**
- Standard tasks (email drafting, calendar suggestions, tool use): **Claude Sonnet**
- Complex tasks (multi-step reasoning, long-context analysis): **Claude Opus** — escalated automatically when confidence is low or context exceeds threshold
- No local Ollama model

The `model-routing` skill configures the routing rules in `.sdlc/project.json` → `models`.

## Consequences

- Cost and latency are optimised per task type.
- Routing rules are reviewed when a new task type is introduced.

## Alternatives

- Always Sonnet — rejected: cost/speed benefit of Haiku for simple tasks is significant.
- Local Ollama — deferred: no privacy requirement identified that justifies the operational overhead.
