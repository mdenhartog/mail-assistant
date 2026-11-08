---
id: ADR-0020
title: "Mail triage: store capped alert content for 30 days"
status: accepted
area: data
tags: [mail-triage, privacy, postgresql, retention]
date: 2026-11-09
guardrails: [guardrail-sqlalchemy-alembic, guardrail-python]
---

## Context

An alert that is held during quiet hours, or a snoozed alert that comes back, is built hours or days after the mail was judged. The daily overview also names the mails the agent was unsure about. The first design stored only ids, hashes and decisions (AC-22), which is not enough to rebuild those messages without fetching and judging the mail again (a second model call on the same text).

## Decision

Marco approved (2026-11-09) storing a small amount of mail-derived content in PostgreSQL, next to the existing `mail_item` and `alert` tables:

- On `mail_item`: sender, subject and `Reply-To` (each capped), the model's `reason` and `summary` (capped as in the schema), whether an attachment exists, the SPF, DKIM and DMARC results, a failure counter, a `completed` flag and a short note.
- On `alert`: which input the agent is waiting for from Marco (`awaiting_input`).
- A new table `overview_log` (one row per day the overview was settled).
- **Never stored:** the mail body, attachments, and the text of Marco's replies after the draft is used (the draft table keeps its body only until it is used or expires, as before).
- **Retention:** the content columns are cleared 30 days after the mail was claimed; ids, label, urgency, confidence and audit entries stay.

## Consequences

- Held and snoozed alerts and the overview are rebuilt from the database, with no extra Gmail or model calls.
- The database now holds personal data (sender, subject, short summary). ADR-0018 still applies; the database user keeps only the rights it needs and backups follow the same 30-day reasoning.
- AC-22 is narrowed to: audit entries carry no content, and no column holds a mail body.

## Alternatives

- Fetch and judge again when the alert is due: rejected (cost, and the answer may change).
- Keep everything forever: rejected (more personal data than needed).
