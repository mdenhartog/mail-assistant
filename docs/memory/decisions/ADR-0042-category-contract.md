---
id: ADR-0042
title: "Category contract: own schema, insert-only list versions, shared category-policy package"
status: accepted
partly_superseded_by: ADR-0053 (decision 5)
area: architecture
tags: [mail-categories, postgresql, contract, shared-package]
date: 2026-11-14
revised: 2026-11-14
guardrails: [guardrail-sqlalchemy-alembic, guardrail-pydantic, guardrail-python]
---

## Context

INT-004 (spec `mail-categories`) lets the user keep a list of categories in the web app, which the agent follows. Like the settings of ADR-0025, the list is written by the api and read by the agent, and the agent owns the migrations. Unlike the settings, the same feature adds plans that only the agent builds and applies. The phase 3 round table found that table-level grants cannot express "own version rows only" and that the api needs a read surface that matches its routes.

## Decision

1. New schema `categories`, migrated only by the agent's Alembic chain (ADR-0025, ADR-0030). The tables are listed in `docs/design/mail-categories-design.md`.
2. **List versions are insert-only.** A new list is a new set of `category` rows for `version = expected + 1`; a deferred constraint trigger allows inserts only for a version created in the same transaction, and a unique key on `(mailbox_id, version)` turns a race into a 409. Nobody updates or deletes list rows. `category_identity(mailbox_id, id)` holds the stable category ids and is the foreign-key target of `category` and `category_label`. Actor, channel and time are derived by trigger, never supplied by the writer (ADR-0030). The audit is filled by a deferred constraint trigger.
3. **The api read surface** is `category`, `list_version`, `category_count` and `gmail_label` (label names only), `plan` and column-level `plan_item` (ADR-0044). The agent maintains the two derived tables. The api has no grant on `filing`, `category_label`, `apply_audit` or `telegram_action`.
4. The agent may insert list versions (seed version 1 from current labels, Undo); until the seed exists the api answers 409 `not-ready` to a save.
5. A new shared package `packages/category-policy` holds the name rules (trim, NFKC, case folding, reserved names "Other" and "Archive", length in code points, no `/` or format characters), the limits, the `Assistant/` label mapping, the decision values and `contract/category_cases.json`, run by agent and api. `schedule-policy` is not extended.
6. The agent learns of list changes by polling a version cursor (`list_cursor`) that moves only after the Gmail effects are done; there is no direct call from the api to the agent (ADR-0041). The api readiness check tests "schema revision at least X", so an R2 migration does not break the R1 api.
7. Every table has a retention period; deletion runs through ADR-0047.

## Consequences

- One validation implementation; a leaked api credential cannot rewrite the Gmail label map, a plan or an audit.
- The api deploy depends on the agent migration.
- A new component `category-policy` in `docs/architecture/model.json`.

## Alternatives

- Extend `schedule-policy`: two responsibilities under a wrong name. Rejected.
- One table group writable by both roles: the api could change label ids and plan items. Rejected.
- Update-in-place rows with `DELETE` for the api: cannot be limited by a grant. Rejected.
- LISTEN/NOTIFY or an api call to the agent: breaks "the components meet only in PostgreSQL" (ADR-0041). Rejected.
