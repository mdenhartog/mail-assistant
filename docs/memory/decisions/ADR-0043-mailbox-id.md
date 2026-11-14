---
id: ADR-0043
title: "Mailbox id on every new table"
status: accepted
area: architecture
tags: [mail-categories, multi-mailbox, postgresql, drift]
date: 2026-11-14
guardrails: [guardrail-sqlalchemy-alembic]
---

## Context

D7 of `mail-categories`: now one mailbox, several agents and mailboxes may come later. The architecture baseline (ADR-0041) lists this as drift item 1; INT-006 needs the same answer.

## Decision

Every new table in schema `categories` (including `plan_item`, `apply_audit`, `plan_decision`, `plan_approval`, `move_back_request` and `telegram_action`) carries a `mailbox_id` (NOT NULL, foreign key to a small table `categories.mailbox` that holds only the id), placed first in every key and unique constraint, including the list version. The repository layer filters on it in every query. The api takes the id from configuration for now. Row-level security and a mailbox choice in the sign-in come with the several-mailboxes feature. Tables in `public`, `settings` and `web_auth` are not changed now.

## Consequences

- Adding mailboxes later needs no change of keys on these tables.
- A repository-level test with two mailbox ids exists from R1 (AC-37).
- The older tables still assume one mailbox; INT-006 or the several-mailboxes feature decides about them.

## Alternatives

- No mailbox id until needed: a later migration of keys on live tables. Rejected.
- Row-level security now: no second mailbox exists to prove it. Deferred.
