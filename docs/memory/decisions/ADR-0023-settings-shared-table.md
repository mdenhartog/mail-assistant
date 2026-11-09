---
id: ADR-0023
title: "Adjustable quiet hours: settings in a shared PostgreSQL table"
status: accepted
area: architecture
tags: [mail-triage, settings, postgresql, web]
date: 2026-11-09
guardrails: [guardrail-sqlalchemy-alembic, guardrail-pydantic, guardrail-oauth2-oidc]
---

## Context

INT-002 makes the quiet hours, the overview time, the snooze default and the time zone adjustable from Telegram (agent) and from the web UI (backend). The agent is a poller with its own PostgreSQL storage (ADR-0019, ADR-0007) and no HTTP server; the backend is a skeleton with only a health endpoint.

## Decision

The settings live in one table in the existing PostgreSQL database. The agent reads them at the start of each run; Telegram writes them through the agent; the web backend reads and writes the same table. The table schema is the contract between the two components. Both validate every write with the same rules. With no row the agent uses the first-release defaults. `time_policy` is rebuilt to take the settings as an argument instead of module constants (no flag, no second code path).

## Consequences

- Telegram (part 1) ships without the web backend; the web part (part 2) adds a backend module on the same table.
- The agent keeps working when the backend is down; a failed read falls back to the last values read, or the defaults.
- Two components share one schema, so schema changes need a migration owner and a contract test on both sides (decided in phase 3).
- Validation rules are written twice (Python agent, Python backend); a shared rule set or package is a phase 3 decision.

## Alternatives

- The backend as only owner, the agent reads over an API: Telegram would depend on the backend and a service credential; rejected for part 1.
- The agent exposes an API to the backend: the agent has no server; most work and not in line with ADR-0019; rejected.
