---
id: ADR-0025
title: "Settings contract: own schema, agent-owned migrations, shared policy package"
status: accepted
area: architecture
tags: [mail-triage, settings, postgresql, contract]
date: 2026-11-09
guardrails: [guardrail-sqlalchemy-alembic, guardrail-pydantic, guardrail-python]
---

## Context

ADR-0023 shares one table between the agent and the backend; ownership, roles, concurrency and audit were left open. The round table of 2026-11-09 found that the agent migrates a single schema holding mail and token tables, so a backend role could not be limited, and that two writers on one row lose updates.

## Decision

The settings live in a PostgreSQL schema `settings`, migrated only by the agent's Alembic chain: `settings.schedule` (single row, `CHECK id = 1`, a `version` column) and `settings.settings_change` (append-only, filled by a trigger with time, channel, actor, old and new). Every write replaces the whole row, validated as a whole, with a version check. CHECK constraints enforce the range rules as a backstop. One shared Python package `packages/schedule-policy` holds the validation and the `TimePolicy` model and is used by the agent and the backend; a contract test runs in both. Neither runtime role owns tables; the backend role gets only what it needs on `settings`; the audit table accepts inserts only.

## Consequences

- One validation implementation; the database refuses what the code would refuse.
- The backend's rights can be proven small (no access to mail, alert content or tokens).
- The backend deploy depends on the agent migration (readiness check on schema version).
- Refines ADR-0023; the table name there means `settings.schedule`.

## Alternatives

- Two validation copies: drift. Rejected.
- Backend as only owner: rejected in ADR-0023.
- Database rules only: a valid zone name cannot be expressed in SQL.
