---
id: ADR-0063
title: "Resort plan as a series of parts with a watermark cursor and a bounded notice"
status: accepted
area: architecture
tags: [daily-budget-partial-plan, mail-triage, plan, api, web, security]
date: 2026-11-26
guardrails: [guardrail-python, guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-gmail, guardrail-telegram]
---

## Context

A plan becomes reviewable only when every mail is checked, so a paused build blocks the user (INT-011). ADR-0056 gives one request, two plans (`auto`, `review`) and one non-terminal plan per mailbox and kind. The request is insert-only, and the cursor is a Gmail message id that restarts at the top when the mail is gone (threats T-03, T-07 to T-14).

## Decision

1. **Parts.** When the budget (or the pace) stops a build with at least one mail checked, the checked mails close as one part: an ordinary `auto` and `review` pair with `part_no` and `start_cursor`. With nothing checked the build keeps waiting. Unique (request, kind, part).
2. **Series.** The parts of one request are a series. The request stays insert-only and carries no cursor. `start_cursor` of part N+1 is copied from the end of part N by a BEFORE INSERT trigger; the cursor only moves forward. The next part starts on the next budget day and only when the previous part has no non-terminal plan. The 5 000-mail cap counts the whole series. A build lease and a cursor compare-and-set keep two instances from judging the same mail.
3. **Cursor form.** The position is an internalDate plus message id watermark. When the position cannot be found the series pauses with `cursor_lost`; it never restarts at the top. A mail on which the model fails 3 times is recorded as unclear and the series goes on past it.
4. **Series end.** A series ends on Cancel, Undo or Lock of any part, a web lock, a list change, the cap, a part open for 14 days (`expired`), or a series age of 14 days. The system never approves a part of an ended series. `POST /api/resort-requests` answers 409 while a series is unfinished.
5. **Notice.** The existing "plan ready" message is the one message: part number, counts, and that the rest continues. One per UTC day (a database record), but the notice of an `auto` part with items is never suppressed, and such a part cannot become `applying` while `announced_at` is empty. Nonces are tied to plan and chat. Counts and fixed words only.
6. **Plan view.** The view adds part, series totals and `pause_reason` from a fixed set (`budget`, `pace`, `waiting_for_part`, `cursor_lost`, `expired`, `ended`) with a CHECK and a `Literal`. The web role gets column-level SELECT on `categories.plan` without the cursor columns. Logs and audit hold integers, fixed values and plan uuids.

## Consequences

- Migration: part and cursor columns, `announced_at`, a notice record, the trigger, the grants and the CHECK. Contract change of the plan view: rebuild, no flag.
- Extends ADR-0056 and ADR-0046 (build); ADR-0047 gets the column grants.
- Accepted risk AR-C: within the series age of 14 days the threshold of day 1 approves later parts.

## Alternatives

- One growing plan that the user releases item by item: rejected in ADR-0056 (one frozen plan per approval source).
- A cursor on the request: breaks insert-only. Rejected.
- Restart at the top and skip checked mails by a lookup: pays again when the lookup misses. Rejected.
