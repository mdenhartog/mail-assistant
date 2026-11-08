---
id: ADR-0006
title: GxP relevance: not a GxP system
status: accepted
area: gxp
tags: [gamp5, validation]
date: 2026-11-08
guardrails: []
---
## Context
GAMP 5 determines whether functions may be executed in production and whether a formal validation package is required.

## Decision
The mail assistant does **not** create, change, or use GxP records, and does not support GxP decisions. The GAMP 5 validation track is **off**.

Reason: the application manages personal email and calendar data for productivity purposes; it has no connection to regulated manufacturing, laboratory, or clinical processes.

## Consequences
- No `validation/` directory or validation package required.
- No QA approver gate on the production release.
- This ADR is revisited if a future spec touches GxP triggers (audit trail, electronic signature, batch record, LIMS integration).

## Alternatives
- GxP applicable — rejected: no regulatory context identified.
