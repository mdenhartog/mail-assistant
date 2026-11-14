---
id: ADR-0044
title: "The api reads sender and subject of plan items; accepted exposure MR-1"
status: accepted
area: security
tags: [mail-categories, privacy, postgresql, web]
date: 2026-11-14
guardrails: [guardrail-sqlalchemy-alembic, guardrail-fastapi]
---

## Context

ADR-0025 says the backend role has no access to mail content. The review page of `mail-categories` must show sender and subject of the mails that would move (D10). The user accepts that anyone who can sign in to the web app sees them (D13).

## Decision

1. ADR-0025 is narrowed from "no access to mail content" to "no access to mail bodies, alert content and the Gmail token". The api role may read, through column grants, only the sender (display name and address) and the subject (cut to 120 characters) of plan items.
2. Sender and subject live only in `plan_item`. They are removed when the plan is applied, or 14 days after the last decision or the replacement of the plan. The apply audit and the rejection table never hold them.
3. They are never put in a log, a URL (so no sender search or filter in a query string), an error body (also not from a trigger or function), Sentry or a Telegram notice; responses carry `Cache-Control: no-store`. The api reads only the columns `sender_name`, `sender_address`, `subject`, the old and new category, `decision`, `state` and `reason`.
4. Accepted risk MR-1 (threat model `mail-categories`): whoever can sign in, including someone who reads the user's mailbox (R-1 of web-settings), sees them. Reviewed on 2027-05-10 with R-1. This adds to ADR-0018, it does not replace it.

## Consequences

- The api role is wider than for settings, but only by two columns of one table; AC-20 and AC-27 prove the rest stays closed.
- Third-party personal data is shown in the browser; the retention is short.

## Alternatives

- Show only counts and message ids: the user cannot judge a move. Rejected (D10).
- Fetch sender and subject from Gmail on demand through the agent: needs a request path from api to agent (ADR-0041) and a longer-lived Gmail read. Rejected.
