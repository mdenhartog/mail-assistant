---
feature: daily-budget-partial-plan
intent: INT-011
spec: docs/specs/daily-budget-partial-plan.md
status: draft
date: 2026-11-26
---

# Threat model: a higher daily budget and a plan in parts

## Scope

Components: the mail-triage agent (the stored budget, the build in parts, the series cursor, the notice), PostgreSQL
(a budget ledger, part columns on the plan, grants), the api (read-only plan view) and the web ("Review moves").
Third parties: Anthropic (cost and data sent out), Telegram (notice and buttons), Gmail (listing and the cursor).
Out of scope: how mail is judged, the threshold and the apply flow, except where a series changes them.

## What the code shows today

1. The budget is a counter in memory (`DailyBudget`) on the agent's own UTC clock; the check and the spend are two steps.
2. One counted call can be up to three HTTP requests (`ModelPoster` retries), but the budget counts one.
3. The cursor is a Gmail message id; when that mail is gone `GmailBuild._scan_for` restarts from the top.
4. The build has no lease and `record_progress` does not check the cursor.
5. A model refusal does not move the cursor, so the next run spends again on the same mail.
6. `resort_request` is insert-only; `request_resort` accepts a new request whenever no plan is open, which is true between parts.
7. The api role has table-level SELECT on `categories.plan`, including `build_cursor`.

## Data classification

| Data | Class | GDPR |
|---|---|---|
| Budget ledger (UTC day, calls per purpose) | internal | no |
| Series cursor (internalDate and Gmail message id) | confidential, a pseudonymous mail identifier | yes |
| Part number, checked counts, series total, pause reason (fixed values) | internal | no |
| Plan items (sender, subject) | personal data (unchanged) | yes |
| Trimmed mail text sent to the model | confidential personal data, about 2.5 times more per day | yes (same processor and purpose) |
| Telegram notice (fixed words and whole numbers) | internal | no |
| `DAILY_MODEL_BUDGET` | internal configuration | no |
| Anthropic API key | secret (unchanged) | no |

Trust boundaries: Gmail into the agent (untrusted content), the agent to Anthropic (where cost is spent), the agent
role and the web role to PostgreSQL, the browser to the api (session and CSRF), the agent to Telegram and back.

## STRIDE assessment

| Type | Assessment | Residual |
|---|---|---|
| Spoofing | No new authentication. A stolen session can file a new "Sort again"; a forged Telegram callback could aim Cancel at another part; a second agent instance has the same identity. Controls: session and CSRF, webhook secret and chat allow-list, nonces tied to one plan, a lease. | low to medium |
| Tampering | The budget row or the cursor could be moved (pay twice, skip mail); a cursor stored on the insert-only request would break its rule. Controls: a definer function for spending, trigger-copied start cursor, column grants. | medium until in place |
| Repudiation | A part is approved by the system days after the request. Controls: request id, part number and database times on every part; the ledger by purpose; `plan_approval` with channel `system`. | low |
| Information disclosure | The plan view could carry model error text or the cursor; logs could carry the cursor or label names; 2.5 times more mail text goes to the processor. Controls: fixed pause reasons, column grants, integer-only logs. | low to medium |
| Denial of service | A restart doubles the budget; a poison mail loops; a flood drains the budget; the plan starves new mail; an open part holds the series; a deleted cursor mail restarts the series. | medium to high |
| Elevation of privilege | A later part could auto-move mail after Cancel or Lock on an earlier part; the once-a-day rule could suppress the notice that carries Cancel; the web role could get write rights on the budget; a call path could skip the budget. | high until the series-end rules exist |

## Threats

L = likelihood, I = impact. ASVS 4.0.3, level 2.

| id | element | STRIDE | threat | L | I | mitigation | criterion | ASVS |
|---|---|---|---|---|---|---|---|---|
| T-01 | budget | D | A restart gives a second budget of up to 500 calls | M | M | A ledger row per mailbox and UTC day; the day comes from the database clock | SAC-1 | 11.1.4 |
| T-02 | budget, two instances | T, D | Check and spend are separate, so two instances over-spend and judge the same mail | M | M | One atomic conditional spend in a definer function; a build lease and a cursor compare-and-set; unique (request, kind, part) | SAC-2, 3 | 1.11.2, 11.1.6 |
| T-03 | build loop | D | A poison mail keeps the cursor still and burns the budget every day | M | M | Count attempts per position; after 3 failed attempts the mail is unclear and the cursor moves on; every HTTP attempt counts | SAC-4, 5 | 11.1.4, 11.1.7 |
| T-04 | incoming mail | D, T | A flood drains the budget; injected text forces the second call | M | L | The budget is the bound (accepted, AR-A); at most `CALLS_PER_MAIL` calls per mail; the screen shows the reason | SAC-6 | 11.1.5 |
| T-05 | reserve | D | The plan spends 450 calls in the UTC night and new mail (about 170 mails a day) has 50 left | H | M | Pace the plan's share over the UTC day | SAC-7 | 11.1.4 |
| T-06 | ledger | T, E | The web role writes the ledger; an agent bug lowers it | L | M | Web role: no right (42501); agent: SELECT and EXECUTE of the spend function only; a trigger refuses a decrease or a re-dated row; purge | SAC-8 | 4.1.3 |
| T-07 | series cursor | T | A cursor on the request breaks the insert-only rule; the agent picks any start cursor | M | M | No cursor on the request; each part carries `part_no` and `start_cursor`, copied by a BEFORE INSERT trigger from the previous part; the cursor only moves forward | SAC-9 | 11.1.1 |
| T-08 | cursor and Gmail | D, T | The cursor mail is deleted and the scan restarts at the top, so mail is paid for again | H | M | An internalDate and id watermark; never restart within a series; if the position is lost the series pauses with reason `cursor_lost` | SAC-10 | 11.1.1 |
| T-09 | `POST /api/resort-requests` | S, D | Between parts no plan is open, so a new request restarts from the top and pays again | M | L | `request_resort` refuses with 409 while a series is unfinished | SAC-11 | 11.1.2 |
| T-10 | open part | D | A review part never approved holds the series for ever | M | L | The screen says it waits for part N; a part open longer than 14 days ends the series with reason `expired` | SAC-12 | 11.1.5 |
| T-11 | series consent | E | After Cancel, Undo or Lock on part 1 the next part is system-approved again | M | H | Cancel, Undo, Lock or a web lock on any part ends the series; a series has a maximum age of 14 days; the system never approves a part of an ended series | SAC-13 | 4.1.5 |
| T-12 | Telegram notice | R, E, S | The once-a-day rule or a failed send suppresses the notice of an `auto` part that carries Cancel; two instances send twice; a nonce is replayed on another part | M | H | The once-a-day rule is a database record per mailbox and UTC day but never suppresses the notice of an `auto` part with items; a part cannot become `applying` while `announced_at` is empty; nonces tied to plan and chat | SAC-14, 15 | 4.1.5, 7.1.2 |
| T-13 | api plan view | I | The view shows error text, the cursor or another mailbox's plan | L | M | `pause_reason` is a fixed set with a CHECK and a `Literal`; the web role has no SELECT on the cursor columns; the mailbox comes from settings | SAC-16 | 4.2.1, 8.3.4 |
| T-14 | logs and audit | I, R | Logs carry the cursor, model error text or label names | M | M | Integers, fixed values and plan uuids only; one audit line per part close, wait and series end | SAC-17 | 7.1.2 |
| T-15 | configuration and call paths | E, D | A mistyped budget (50000) or a call path that skips the spend function | L | H | Settings bound `reserve + 2` to 1000; an architecture test that every model call goes through the spend function; a provider-side spend limit as an operations control | SAC-18 | 1.14 |
| T-16 | data to the model | I | About 2.5 times more mail text goes to the processor per day | M | L | `trim_mail` cap unchanged; recorded in the processing register (accepted, AR-B) | existing tests | 8.3 |

## Security acceptance criteria

- **SAC-1:** Given 120 calls spent today, When the agent restarts, Then 120 still count, and the day is the database's UTC date.
- **SAC-2:** Given 3 calls left above the floor, When two sessions each try to spend 2 at the same time, Then exactly one succeeds and the ledger never exceeds the limit.
- **SAC-3:** Given two agent instances, When both run the build, Then each mail of a series is judged at most once and only one part N+1 exists per kind.
- **SAC-4:** Given a mail on which the model refuses or times out 3 times, When the build runs again, Then it is recorded as unclear, the cursor moves past it and no further call is spent on it.
- **SAC-5:** Given the model answers 429 twice and then 200, When one judgement is made, Then the ledger counts every attempt that reached the provider.
- **SAC-6:** Given a mail whose text tells the model to be unsure, When it is judged, Then at most `CALLS_PER_MAIL` calls are made for it.
- **SAC-7:** Given the build runs at 00:30 UTC with a full budget, When it spends, Then it stops at the paced share, and the day's new mail still gets its calls.
- **SAC-8:** Given the web role, When it reads, writes or calls the spend function, Then it is refused (42501); given the agent role, When it updates the ledger or lowers a count, Then it is refused.
- **SAC-9:** Given part 1 ended at cursor C, When the agent inserts part 2 with another start cursor or number, Then the stored values are C and 2; the agent cannot UPDATE `resort_request` (42501).
- **SAC-10:** Given part 1 ended at mail M and M was deleted, When part 2 starts, Then it continues after M's date and no mail of part 1 is judged again.
- **SAC-11:** Given a series with part 1 applied and part 2 not started, When a new request is sent, Then 409 and nothing is stored.
- **SAC-12:** Given a review part open for 14 days, When the next budget day starts, Then the series ends with reason `expired` and one counts-only notice says so.
- **SAC-13:** Given Cancel, Undo or Lock on any part, When the next budget day starts, Then no further part is built or approved.
- **SAC-14:** Given an `auto` part with items whose notice was not sent, When its `apply_after` passes, Then it does not become `applying`.
- **SAC-15:** Given the Cancel button of part 1, When it is pressed after part 2 exists, Then only part 1 is affected or it is refused as used; given a callback from a chat that is not allowed or with a wrong secret, Then it is refused.
- **SAC-16:** Given a signed-in session, When the plan of a paused part is read, Then the body holds the part, the totals and one fixed pause reason, and no cursor, message id, sender, subject or error text; without a session 401; the web role cannot select `build_cursor` (42501).
- **SAC-17:** Given a part closes, waits or a series ends, When logs and audit are captured, Then they hold only integers, fixed values and plan uuids (a test with planted sender, subject, label name and message id finds none).
- **SAC-18:** Given `DAILY_MODEL_BUDGET` of 10 or 50000, When the agent starts, Then settings validation fails; given the code, When the architecture test runs, Then every model call goes through the spend function.

## Accepted risks (owner: the user; each needs an ADR)

- **AR-A:** A mail flood can use the whole budget so that the plan does not progress. Bounded by the budget; the screen shows the reason. Review after 90 days.
- **AR-B:** About 2.5 times more trimmed mail text goes to the model provider. Same processor and purpose.
- **AR-C:** Within the maximum series age of 14 days the threshold of day 1 approves later parts.

## Decisions that need an ADR (phase 3)

1. Stored model-budget ledger (amends ADR-0021): the table, the spend function, the database UTC day, the purpose split, counting HTTP attempts, an upper bound on the setting, grants and retention.
2. Plan series in parts (extends ADR-0056, ADR-0046): parts as plan pairs with `part_no` and a trigger-copied `start_cursor`, an insert-only request, unique (request, kind, part), the build lease, series-end rules, `request_resort` refusing during a series.
3. Cursor form: an internalDate and id watermark instead of a message id with a fall-back to the top (touches `guardrail-gmail`).
4. Pacing of the plan's share of the budget (reopens D8 of the spec).
5. The notice rule: one per UTC day, never suppressing the notice of an `auto` part, `announced_at` before apply.
6. The plan view contract: fixed pause reasons and column-level SELECT for the web role on `categories.plan` (extends ADR-0047).
7. Accepted risks AR-A, AR-B and AR-C.

## Open questions

- Pacing: which rule fits, a share of `(limit - reserve) * hour / 24`, or a reserve sized to the new-mail volume of the last 7 days? (the user, phase 3)
