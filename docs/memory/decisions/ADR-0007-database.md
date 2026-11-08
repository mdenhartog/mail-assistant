---
id: ADR-0007
title: "Database: PostgreSQL, no vector or time-series extension"
status: accepted
area: database
tags: [postgresql, database]
date: 2026-11-08
guardrails: [guardrail-sqlalchemy-alembic]
---
## Context

The backend needs a relational database. Additional stores for vector search, time series, cache, and full-text search were evaluated.

## Decision

- Relational: **PostgreSQL** (managed via SQLAlchemy + Alembic)
- Vector search: **none** — no pgvector extension; no semantic retrieval required at this stage
- Time series: **none** — no TimescaleDB extension; standard Postgres handles counts and simple analytics
- Cache / queue: **none** — no Redis or Celery; no background task volume that justifies the operational cost
- Full-text search: Postgres built-in FTS is sufficient

## Consequences

- Compose stack has a single `postgres` service; fewer moving parts to secure and back up.
- Each decision (vector, time series, cache) is revisited when a spec demonstrates the need.

## Alternatives

- pgvector — deferred: no RAG or semantic-search spec identified yet.
- TimescaleDB — deferred: no time-series analytics spec identified yet.
- Redis — deferred: no high-volume caching or async task spec identified yet.
