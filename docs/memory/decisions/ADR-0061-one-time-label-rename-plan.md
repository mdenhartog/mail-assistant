---
id: ADR-0061
title: One-time label rename plan and its agent-api seam
status: accepted
area: architecture
tags: [label-prefix-removal, mail-triage, api, postgresql]
date: 2026-11-24
guardrails: [guardrail-gmail, guardrail-sqlalchemy-alembic, guardrail-fastapi]
---
## Context

Existing `Assistant/` labels must lose the prefix without losing mail, and `list_sync` would otherwise rename them at once, before the user has seen anything.

## Decision

1. A per-mailbox state `label_migration` (`pending`, `confirmed`, `done`) gates every label write.
2. The agent builds the plan (`label_rename_item`: id, old name, new name, mail count, action rename or merge, state) and the api shows it as a preview with a skip per label. A clash with an existing label is a merge (D8): add the existing label to the mails and remove the old one, idempotent.
3. The api writes an insert-only confirmation through a `SECURITY DEFINER` function, the pattern of `request_resort`, carrying the plan hash over (id, old name, new name). The agent reads each id again and skips an entry that was changed by hand.
4. A backup of the old names and ids allows a restore by id and is deleted after the retention period. Migration 0030 expands (`managed_label`, rename tables, state, timers, settings, nullable fields); 0031 contracts (drops `category_label`, `gmail_label` and `adoptable`) in a later release.
5. The waiting time, protection period and retention live in the `settings` schema; the name of "Other" lives in `list_settings`.

## Consequences

- The api never calls Gmail. A merge moves mail between two labels, so it is the only mail write of this feature and runs through the narrow adapter only.
- Settles drift item 2 of the placement guide (a web read of agent-produced data).

## Alternatives

- Rename on the first sync: no preview, breaks the rule that nothing changes before the user confirms.
- Leave old labels: two forms of a name, rejected by the spec.
