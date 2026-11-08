---
id: ADR-0009
title: "Design process: clickable prototype per feature"
status: accepted
area: design-process
tags: [prototype, ux, design]
date: 2026-11-08
guardrails: []
---
## Context
The team must decide whether to build a clickable prototype in Claude Design before writing code, for each feature.

## Decision
Prototype production is **per feature**: the spec for each feature decides whether a Claude Design clickable prototype is built in phase 3 before implementation begins.

Criteria for requiring a prototype:
- Feature introduces a new screen or interaction pattern
- Significant user-facing complexity or ambiguity in the UX flow
- Stakeholder alignment needed before build

## Consequences
- Features with simple, well-understood UI (e.g. a settings toggle) can skip the prototype step.
- Phase 3 of each feature records the prototype decision.

## Alternatives
- Always — rejected: low-complexity features do not benefit enough to justify the extra step.
- Never — rejected: high-complexity features risk costly rework without early UX validation.
