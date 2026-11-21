---
id: ADR-0053
title: "Category contract v2: nested names, kinds, senders, ticks, list-level settings"
status: proposed
area: architecture
tags: [label-structure, mail-categories, postgresql, contract, shared-package]
date: 2026-11-21
supersedes: ADR-0042 (decision 5 only; the rest of ADR-0042 stays in force)
guardrails: [guardrail-sqlalchemy-alembic, guardrail-pydantic, guardrail-python]
---

## Context

INT-008 (spec `label-structure`) needs names that nest (`Huis/Energie`), a topic and an extra label per mail, sender entries per category, an "always notify" tick, long descriptions, general instructions for the whole list and the archive label name. ADR-0042 fixed a contract with a name, a description, no `/` in names, 500 characters and 50 categories (decision 5, spec C-3 of `mail-categories`). The user called the `/` rule a mistake (D2).

## Decision

1. The `category` table gets `kind` (`topic` or `extra`, default `topic`) and `notify` (boolean, default false). A new insert-only table `category_sender` holds one row per sender entry (`mailbox_id`, `version`, `category_id`, `entry`, `is_domain`, `subdomains`). A new insert-only table `list_settings` holds, per list version, `general_instructions` and `archive_label`. All three follow the insert-only version rules of ADR-0042 (deferred constraint trigger, `(mailbox_id, version)` key, api and agent may insert).
2. `filing` is rebuilt: `topic_id` and `extra_id` replace `category_id`; it also records `source` (`model`, `sender_rule`, `sender_rule_not_applied`) and `source_ref` (the matched entry, the only personal data in the table, kept under the one-year retention of `filing`).
3. `packages/category-policy` is rebuilt as v2: name rules **per segment** (look-alikes of `/` fold to `/`, first segment not "Archive" or "Other", whole label at most 225 characters), kinds, sender entry rules and the pure matcher, the refused domain lists (public mailbox providers, multi-tenant sending platforms), limits (description 1 500, general instructions 4 000, 100 entries per category, 100 categories), the confidence scale and the YAML schema (`schema: 1`) of upload, export and template, and `contract/category_cases.json` run by agent and api.
4. **One confidence scale:** the model's confidence stays a float from 0 to 1; the plan stores `confidence_pct = round(confidence * 100)` (half up) and compares it with the threshold in whole percent, "at or above". `LOW_CONFIDENCE = 0.6` keeps its meaning for **new mail** only (filing under "Other"); it has no relation to the plan threshold.
5. The migration (agent's Alembic chain, ADR-0025) adds the columns and tables with defaults to the existing rows: every category becomes a topic with no senders and no tick; it inserts **no** list version and no audit record; it is idempotent and has a working downgrade (the downgrade copies `topic_id` back to `category_id`).

## Consequences

- Supersedes decision 5 of ADR-0042; its decisions 1 to 4, 6 and 7 stay.
- Rebuild of `category-policy`, of `filing` and of the list read and write paths in the agent and the api (rebuild-not-patch).
- The api deploy depends on the agent migration, as before.
- One validation implementation for typed saves, uploads and the agent.

## Alternatives

- Put senders as a JSON column on `category`: cannot be limited or checked by constraints, hard to index for the matcher. Rejected.
- Insert a list version 2 in the migration: would fire the audit trigger as if the user had edited the list. Rejected.
- Keep `category_id` and add `extra_id`: leaves a column whose meaning changed. Rejected (rebuild-not-patch).
