---
id: ADR-0047
title: "Database functions are the api's only write path for plan decisions; retention runs through an owner-role purge"
status: accepted
area: security
tags: [mail-categories, postgresql, audit, retention, grants]
date: 2026-11-14
guardrails: [guardrail-sqlalchemy-alembic, guardrail-python]
---

## Context

The phase 3 round table (architect, security) found that item-by-item decisions have no commit point, that a decision trigger races the agent's state change, that the rolling 24-hour threshold and the decision audit have nothing to count, and that no role is named to delete expired rows when the audit tables are append-only.

## Decision

1. The api changes plan decisions only through `SECURITY DEFINER` functions `record_decision` and `approve_plan`, owned by a non-login role, `search_path` pinned, revoked from `PUBLIC`, executable only by the api role. Each locks the plan row `FOR UPDATE`, checks state and item count (a mismatch is a 409 error), writes an append-only record (`plan_decision`, `plan_approval`) with channel and actor digest derived from the session role (ADR-0030), and returns no row values in errors.
2. No runtime role has `UPDATE` or `DELETE` on decision or audit data. The agent has no `DELETE` on audit tables.
3. Retention: every table has a retention period (see the design). An owner-role function `purge_expired()` with **no parameters** uses the database clock and deletes only rows past their retention; the agent calls it and cannot influence what it deletes. Tests backdate rows with owner fixtures; a test shows that, whatever the agent supplies or does, rows younger than their retention survive, and that a direct `DELETE` by the agent is refused with SQLSTATE 42501.
4. The functions build no SQL from their arguments, check the shape of `scope`, that every id belongs to the given plan and mailbox, at most 200 ids and the group count, and that the plan's mailbox matches the caller's.

## Consequences

- One locked transaction per approval removes the race; the 24-hour threshold is countable from `plan_approval`.
- The functions are database code that needs real-PostgreSQL tests (privilege matrix, races, retention with a fake clock).
- Extends ADR-0030 (least privilege, server-derived actor) and ADR-0042.

## Alternatives

- Decision trigger with a column `UPDATE`: races the agent. Rejected.
- Agent polls approval rows and decides alone: no atomic commit point. Rejected.
- `purge_expired(now)` with a caller-supplied clock: the agent could pass a future time and wipe the audit. Rejected.
- A purge CronJob with owner credentials: a standing job with wide rights (as rejected for web-settings). Rejected.
