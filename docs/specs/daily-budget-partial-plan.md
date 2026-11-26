---
feature: daily-budget-partial-plan
intent: INT-011
status: draft
revision: 2 (phase 2 threat model: D3, D7, D8 changed and D9 to D13 added; waiting for the user)
date: 2026-11-26
approved: 2026-11-26 (revision 1, the user, phase 1 gate; revision 2 not yet approved)
approver: the user
depends_on: mail-categories, label-structure, mail-triage, web-settings
---

# A higher daily model budget and a plan in parts

## Summary

The agent may make 200 model calls per day and keeps 50 for new mail. New mail uses most of that (about 170 mails
a day), so the plan for older mail ("Sort everything again") is paused almost every day. The plan only becomes
reviewable when every mail is checked, so the user cannot review or apply anything, and the "Review moves" screen
only says "checked so far" without a reason (INT-011).

After this change:

- The daily budget is **500 model calls**. The reserve for new mail stays 50.
- When the budget runs out during a plan, the checked mails become **one part** of the plan. The user can review
  and apply that part. The next day the agent starts the **next part** where the previous one stopped, and so on
  until all mail is checked or the cap is reached (ADR-0056 keeps its 5 000 mails per request).
- The screen says why a plan waits, and one Telegram message per day says that a part is ready and that the rest
  continues.

It extends ADR-0046 (decision 3, build) and ADR-0056 (two plans per request).

## Who it is for

The user, with one mailbox and one agent.

## Goals

1. The daily model budget defaults to 500 calls; the reserve for new mail stays 50 calls.
2. When the budget stops a build, the mails checked so far are one part that the user can review and apply.
3. The next part starts the next budget day, after the mail that was already checked, and only when the previous
   part is finished.
4. The "Review moves" screen shows the part, the total checked and the reason for a pause.
5. The user gets at most one Telegram message per day about this, with counts only.

## Non-goals

- Changing how the model judges mail, the confidence threshold, the sender rules or the apply and move-back flow.
- A second budget or a spending limit with the model provider.
- Releasing single items of an open plan (rejected in ADR-0056: one frozen plan per approval source).
- Changing how new mail is filed.

## Anti-goals (a failure even if it technically works)

- A mail is checked (and paid for) twice for the same request.
- New mail loses its reserve of 50 calls because a plan used the budget.
- A part moves mail before the user approved it, or before the wait that already exists for sure items.
- The budget is used up without the user seeing why a plan waits.

## Decisions (calls of the author, for the user to approve)

| # | Decision | Why |
|---|---|---|
| D1 | The default of `DAILY_MODEL_BUDGET` becomes 500 (agent setting and compose default). The reserve of 50 stays in code. Calls are counted as model calls, not mails (the user's answer, 2026-11-25). | The intent. |
| D2 | A build that is stopped by the budget **closes the part** when it checked at least one mail: the part becomes an ordinary pair of plans (`auto` and `review`) for the mails checked so far. With no mail checked yet it keeps waiting. | One part runs through the existing flow, nothing new to approve. |
| D3 | The **series** (the parts of one request) carries the cursor; the request itself stays insert-only. The next part starts at the next budget day (UTC date), from the end of the previous part, once the previous part has no non-terminal plan. A part the user leaves open holds the series; the screen says so. | No mail is checked twice. One non-terminal plan per mailbox and kind (ADR-0056) stays true. |
| D4 | A list change ends the series (the pending parts are replaced, ADR-0056 point 5). Sort again starts a new series. | D8 and D12 of `label-structure`: a list change never moves old mail. |
| D5 | The 5 000-mail cap counts the whole series. | Same cap as today. |
| D6 | The daily budget count is **stored in the database per UTC day** and not only in memory. A restart does not give a second budget. | At 500 calls a restart could double the spend. |
| D7 | The existing "plan ready" Telegram message is the one message: it says the part number, the counts and, when more mail waits, that the rest continues after this part is done. At most one such message per day, **except** that the notice of a part with sure items (which move without review) is always sent, and such a part does not move mail before its notice was sent. No names, senders or subjects. | The user asked for one message; the Cancel button must never be missing. |
| D8 | The reserve for new mail stays 50 calls and the quiet hours are not changed. Raising the number on the user's own stack needs the user's go-ahead for a deploy. The plan's use of the budget is **paced over the UTC day** (D10). | Standing rule; the threat model found that a plan running at night would leave new mail 50 calls. |
| D9 | **A series ends** when the user presses Cancel, Undo or Lock on any part, when the web is locked, when the list changes, when the cap is reached, when a part stays open for 14 days, or when the series is older than 14 days. The system never approves a part of an ended series. Sort again starts a new series. | Without it the next day's part would move mail after the user said stop (threat T-11). |
| D10 | **Pacing.** Until hour `h` of the UTC day the plan may spend at most `(limit - reserve) * h / 24` calls of the day, so new mail keeps enough calls through the day. The exact rule is decided in phase 3 (ADR); the criterion is that a plan running just after midnight leaves enough for the day's new mail. | Threat T-05. |
| D11 | While a series is unfinished, a new "Sort again" request is refused with 409 and a plain message. | Threat T-09: a new request between parts would pay again. |
| D12 | A mail on which the model fails 3 times (refusal or time-out) is recorded as unclear and the series goes on past it. Every attempt that reaches the model provider counts as a call. | Threat T-03, T-02. |
| D13 | The series position is an internalDate and message id mark; it never restarts at the top of the mailbox. When the position cannot be found, the series pauses with the reason `cursor_lost`. | Threat T-08. |

## Acceptance criteria

1. Given a fresh installation, When the agent reads its settings, Then the daily budget is 500 and the reserve is 50 (happy).
2. Given a build with 60 calls left above the reserve, When the next mail needs 2 calls and fewer are left, Then the build stops with the reason "budget" and the checked mails are closed as part 1 (happy).
3. Given a build that was stopped before it checked any mail, When the budget is empty, Then no part is closed and the plan waits (edge).
4. Given part 1 is applied or otherwise finished, When the next budget day starts, Then part 2 starts after the cursor and no mail of part 1 is checked again (happy).
5. Given part 1 is still open (ready, scheduled or applying), When the next budget day starts, Then part 2 does not start and the screen says it waits for part 1 (edge).
6. Given a list change during a series, When the build runs, Then the open parts are replaced as before and the series ends; no later part starts (edge).
7. Given 5 000 mails were checked over several parts, When the cap is reached, Then no further part starts and the rest is reported as "not looked at" (edge).
8. Given the agent restarts during the budget day, When it counts calls, Then the calls already spent today still count (security).
9. Given new mail arrives while a plan is building, When the budget is low, Then new mail still gets its 50 calls and the plan stops first (happy).
10. Given a part is ready, When the Telegram message is sent, Then it holds only counts and fixed words, and at most one such message is sent per day (security).
11. Given the plan waits for the budget, When the user opens "Review moves", Then the screen says "paused: the daily budget is used, continues tomorrow", shows the checked count and does not claim progress while paused (a11y: the text is plain text, the status is announced politely).
12. Given the screen shows a part, When the total grows over the days, Then it shows the part number and the checked mails over all parts of the series (happy).
13. Given the budget day changes at midnight UTC, When the agent checks the day, Then the count starts again from zero once (edge).
14. Given logs and audit, When a part closes or waits, Then they hold numbers only, never mail text, senders, subjects or label names (security).
15. Given the user pressed Cancel, Undo or Lock on any part, When the next budget day starts, Then no further part is built or approved (security, D9).
16. Given a part is open for 14 days, When the next budget day starts, Then the series ends with the reason `expired` and one counts-only notice says so (edge, D9).
17. Given a series is unfinished, When a new Sort again request is sent, Then 409 and nothing is stored (security, D11).
18. Given a mail on which the model fails 3 times, When the build goes on, Then the mail is recorded as unclear, the series passes it and no more calls are spent on it (edge, D12).
19. Given the mail at the end of part 1 was deleted, When part 2 starts, Then it continues after that mail's date and no mail of part 1 is checked again (edge, D13).
20. Given a part with sure items and no sent notice, When its apply time passes, Then it does not move mail (security, D7).
21. Given two agent instances, When both spend calls, Then the stored count never goes above the limit and no mail is checked twice (security, D6).
22. Given the build runs just after midnight UTC with a full budget, When it spends, Then it stops at its paced share and the day's new mail still gets its calls (happy, D10).
23. Given the plan view of a paused part, When it is read, Then it holds the part, the totals and one fixed pause reason and no cursor, message id, sender, subject or error text (security).

## Architecture fit

- `mail-triage` agent: the budget (`DailyBudget`, now stored), the build (`resort_build`), the plan store and the request cursor.
- `api`: the plan view gets the part, the series total and the reason for a pause (read only; no new write path).
- `web`: the "Review moves" building and waiting states; the Settings page is unchanged.
- No new component and no new external system. Three schema changes are expected (a per-day budget ledger with its spend function, part and cursor columns on the plan, and column grants for the web role on the plan); phase 3 decides the details and writes the ADR.

## Open questions for the next phases

- Phase 2: which of D6 and D7 add a trust boundary or a cost-abuse path that the threat model must cover.
- Phase 3: where the budget count lives and who may write it (the agent only).
