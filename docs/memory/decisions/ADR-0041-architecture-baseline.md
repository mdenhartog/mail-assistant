---
id: ADR-0041
title: "Architecture baseline: 9 code components, 8 outside systems, model approved"
status: accepted
area: architecture
tags: [architecture, baseline, model, drift]
date: 2026-11-14
guardrails: []
---

## Context

The project grew from the scaffold through mail-triage (INT-001 to INT-003) and the web settings page (INT-002, INT-005).
Its components were never recorded as one architecture. The kit (0.6.0) asks for a baseline that every later change is
checked against.

## Decision

The baseline is `docs/architecture/model.json`, described in `docs/architecture/README.md` and drawn in
`docs/architecture/system-architecture.html`. It was proposed by the `architect`, challenged by the `security-architect`
and the `product-owner`, and approved by Marco on 2026-11-14.

- Code components: `mail-triage`, `api`, `web`, `schedule-policy`, `tokens`, `platform`, and the unused scaffolds
  `assistant`, `chat-gateway`, `tools`.
- Outside systems and the datastore are modelled without code paths: PostgreSQL, Gmail, Google OAuth, Anthropic,
  Telegram, SMTP, and (only for the scaffolds) Amazon Bedrock and WhatsApp.
- The agent and the api never call or import each other. They meet only in PostgreSQL schemas (ADR-0023, ADR-0025,
  ADR-0033).
- Several people can use the system, each signing in; the current build is single-tenant.
- Existing parts are recorded as they are. `enforce` is `block`; `node scripts/architecture.mjs check` runs in
  pre-commit, CI and the stop check.

## Consequences

- A new component, a new dependency, a change of data ownership or a placement outside the guide needs a decision-gate
  and an ADR, and a model update in phase 3.
- The nine drift items in the README are open backlog, not decided here: tenancy (INT-004), INT-006 read access to agent
  data, DDL ownership of `web_auth`, the sign-in code mail passing through the agent, the unused scaffolds (kept: they are the start of the wanted chat with the agent in Telegram and WhatsApp), backup,
  observability (ADR-0013), Google Calendar (ADR-0011) and the chart name in ADR-0005.
- INT-006 may not be designed until drift items 1 and 2 are decided.
