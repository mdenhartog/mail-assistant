---
id: ADR-0021
title: "Mail triage: one-time catch-up of unread inbox mail"
status: accepted
area: architecture
tags: [mail-triage, gmail, budget, state]
date: 2026-11-08
guardrails: [guardrail-gmail, guardrail-llm, guardrail-sqlalchemy-alembic]
---

## Context

The agent only handled mail that arrived after it first started. Marco's unread mail from before (213, later 75) was never filed (INT-003). The base spec only says "mail that arrived since the last run".

## Decision

Add a separate `CatchUp` use case, run once after the normal pipeline in each mail cycle. It works from a stored cut-off time (`catchup_state`), lists the unread inbox mails older than the cut-off from Gmail (newest first), and files them with the shared judging code. It spends only the daily model budget above a reserve of 50 calls, creates at most 5 alerts (counted in the database), and marks its mails `backlog`. It finishes when nothing is left and then never runs again.

## Consequences

- One new table (`catchup_state`) and one column (`mail_item.backlog`) in migration 0003; no new scope, service or dependency.
- The normal pipeline is unchanged except that its decision step becomes a shared function (rebuild-not-patch: no flag on the existing path).
- New mail keeps a guaranteed share of the budget; the catch-up may take more than one day.
- The daily budget counter is in memory (as before), so after a restart the reserve of 50 holds only from the next day. Accepted limitation; persisting the count is a later change.
- An abandoned mail stays unread in the inbox and is skipped on every later run.

## Alternatives

- Move the stored Gmail history position back: history is limited in time and cannot select "unread only". Rejected.
- Copy all old ids into a database queue: duplicates what Gmail already knows and can drift. Rejected.
- A Telegram command that starts the catch-up: Marco chose an automatic start. Rejected.
- Treat old mail like new mail when the budget runs out (file as needs-attention): would label old mail urgent only because the budget ended. Rejected (spec AC-B8).
