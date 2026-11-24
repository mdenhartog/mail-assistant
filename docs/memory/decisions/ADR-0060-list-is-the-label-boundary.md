---
id: ADR-0060
title: The category list is the label boundary; managed labels by id; delayed delete of empty labels
status: accepted
area: architecture
tags: [label-prefix-removal, mail-triage, gmail, security]
date: 2026-11-24
supersedes: ADR-0059
guardrails: [guardrail-gmail, guardrail-python, guardrail-llm]
---
## Context

The prefix `Assistant/` marked the scope, was the allow-list of what the agent may change in Gmail, and seeded the first list. INT-010 removes it. ADR-0046 D18 forbids every label delete; the user now allows deleting empty labels (D6, D7 of the spec).

## Decision

1. No label carries `Assistant/`. A label is *managed* when its Gmail label id is the id of a category of the current list, of "Other" or of the archive label. The ids are stored in `managed_label`; names are only a fallback until an id is known.
2. Scope: a mail is in scope when it is in the inbox or carries a managed label; the archive and excluded labels win. The agent adds, removes, creates and renames only managed labels, by id.
3. "Other" (default `Other`) and the archive label (default `Archive`) are settings the user can change. An existing label with a list name is adopted, never refused (D8).
4. The first list comes from the YAML upload, not from Gmail labels (AC-49 of `mail-categories` is retired).
5. Delete: one narrow delete by id. A label is deleted only when it is of type `user`, in no list or setting, targeted by no Gmail filter, has no child, has no mail (counts plus a check that includes spam and trash), has stayed empty for the whole waiting time, left the list at least the protection period ago, and is empty again at the final check. A lease allows one deleting writer. Timers persist per label id; a gap of more than 3 cycles resets them.
6. The waiting time (5 minutes to 12 hours, default 12 hours), the protection period (1 to 30 days, default 7) and the retention of the deleted-label record (7 to 90 days, default 30) are agent settings the user changes in the web UI (D11).
7. All label writes stop until the one-off rename plan is `done` (ADR-0061).
8. No label name appears in a log, audit row, notice or error. The user hears of deletes once a day with counts, and the page shows "recently deleted" for the retention period.

## Consequences

- Security: an adopted user label becomes deletable after it leaves the list. The protection period, the filter check, the double emptiness check and the lease are the controls (threat model T13 to T17).
- Supersedes ADR-0059 in full, D18 of ADR-0046 and the reserved-segment and label-length parts of ADR-0053 point 3.
- Work: `category-policy` v3, a migration, a new delete adapter and a cleanup use case.

## Alternatives

- Keep a prefix: rejected by the user.
- Allow-list by name: breaks on hand renames.
- Delete at once when empty: rejected; Gmail has no conditional delete.
