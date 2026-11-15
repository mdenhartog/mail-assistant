---
feature: mail-categories
intent: INT-004
spec: docs/specs/mail-categories.md
unit: U-mail-categories-19
release: R2
status: open
date: 2026-11-16
---

# Release checklist: mail categories, R2 (re-sorting with "Review moves")

R2 is built on the integration branch but not released. This page says which journeys the end-to-end project `review` covers, which steps only the agent's pytest with fakes covers, what the user must check by hand with the real Gmail, and what the user signs off. Phase 9 (release) is never started without the user's explicit approval; the last row of the checklist is that approval.

## What ran, and where

The prod-like stack has `db`, `mail`, `api`, `web` and `edge`. It has no agent, no fake Gmail and no fake Telegram (the same limit as R1, see `mail-categories-r1.md`: the agent calls fixed Google and Telegram addresses). So the plan, its items and the decisions are put into the database by owner SQL (`apps/web/e2e/support/reviewDb.ts`), as `categories.spec.ts` does for the list. Where the agent would change the plan (apply, cancel), the same SQL does it through the plan's state guard.

| Half | Where | What it proves |
| --- | --- | --- |
| The page, the api and the database | `apps/web/e2e/review.spec.ts`, project `review` (after `categories`), over the prod-like stack: real browser, HTTPS edge with certificate checks on, TLS database | What the user sees and presses; what the api stores (decisions, state `scheduled`, the wait, the move-back request); 401 under the lock; axe and overflow; canary in no log |
| The agent with a fake Gmail and a fake Telegram on a real PostgreSQL | `agents/mail-triage/tests` (the agent's pytest, not Playwright) | Building the plan from a changed list and at the first R2 start, the canary scan of the agent's own logs and notices, applying (the Gmail label moves), skipping a mail the user moved, Move back in Gmail, the Telegram Cancel button, the delay above the threshold, the result notice |
| Every state of the page at four widths, light and dark, 200 % text | `apps/web/e2e/ui-states.spec.ts` (stubbed api, no Docker) | axe, overflow, target size, including states the real stack cannot reach (building, cap reached, failures) |

### Journeys against the criteria of U-mail-categories-19

| Criterion | Journey | Covered by Playwright | Covered only by pytest with fakes |
| --- | --- | --- | --- |
| 1 (AC-9, AC-13, AC-14, AC-41) | A plan is ready, the user approves the group, the plan is scheduled; once applied, Move back records one request | Approve and the stored decisions, state `scheduled`, applied banner, Move back dialog and exactly one request (tests 1 and 2) | "A changed list makes a plan appear" (the build); the mail moving in Gmail; Move back restoring the label in Gmail |
| 2 (AC-42) | An approval above the threshold waits; Cancel stops it | The wait is about the configured delay; the page shows "This review was cancelled." after the plan is cancelled (test 3) | The Telegram Cancel button itself (the cancel here is a SQL update standing in for it); that no mail moved after Cancel |
| 3 (AC-23) | Axe and overflow, four viewports, 200 % text | no review, ready, group open, summary, scheduled, cancelled, applied at 320, 375, 768 and 1280 px; ready and group open at 200 % text | Not applicable |
| 4 (AC-30) | Canary strings in sender and subject | The canary is in no log of edge, web, api, db or mail after the page has shown and approved the mails (the logs are shown to hold the requests) | The agent's own logs, notices and errors |
| 5 (AC-45) | The sign-off line | See "Sign-off of AC-45" below | Not applicable |
| (AC-54) | First plan at the first R2 start | Not run in a browser | Agent pytest only |

### Status of the run

The journeys were written and type-checked (`tsc`, ESLint, `playwright test --list` shows the project `review`), but they have **not been run against the prod-like stack**. The worktree has no `.env` for the stack, and the stack needs its own secrets, certificates and a browser that trusts the private CA; none of that was created from this unit, and the stack the user runs for their own work was not touched. The first green run belongs to the CI job `prod-like` or to the person who sets up a stack with its own compose project name and ports. Until then every row above that says "Playwright" is written but unproven; the first run may need small selector fixes.

## AC-32 note: lock is a 401 and the sign-in page

AC-32 as built for the web: a locked web answers 401 to every plan call and the page returns to the sign-in page. It does not say how to unlock, because the lock must leave no trace on the web (decision in the spec; the unlock is `/web_unlock` in Telegram, and the sign-in page says how to unlock where the spec requires it). Test 4 of `review.spec.ts` checks the 401 and the fall-back to sign-in, and that the plan and its items are unchanged.

## Open points

1. The agent half of every journey is covered by pytest with fakes only (table above). A browser journey with the agent needs fake Gmail, Google token and Telegram services in `deploy/prod-like/` and settings in the agent for their addresses (open point 1 of the R1 checklist).
2. The apply time and the Cancel in the journeys are set by SQL; if the agent's guard or the table names change, `support/reviewDb.ts` changes with them.
3. The `review` project resets the one mailbox, the sign-in tables and the plan tables, so it runs after `journey` and `categories`, by itself.

## Checklist

| # | Item | Owner | Evidence needed | Status |
| --- | --- | --- | --- | --- |
| 1 | The CI job `prod-like` runs the projects `categories` and `review` green with certificate checks on. | Build | The job log. | Open (not yet run) |
| 2 | The agent's pytest for R2 (plan build, first R2 start, apply, skip, Move back, Cancel, threshold wait, notices, canary) is green. | Build | The test run. | Open |
| 3 | **Manual smoke test with the real Gmail (mandatory).** On the local stack with the real mailbox: change the list, wait for the plan, open "Review moves", approve one small group, see the label change in Gmail, press Move back and see the labels restored, approve a group above the threshold and press Cancel in Telegram, check that Telegram shows the result. No fake covers this. | The user | A dated note: what worked and what did not, with the number of mails moved. | Open |
| 4 | Gmail OAuth consent screen is "In production" (row 15 of `web-settings-prod.md`). | The user | The status with its date. | Open |
| 5 | AC-32 understood: the lock is a 401 and the sign-in page (note above). | The user | A dated note that this is accepted. | Open |
| 6 | **User acceptance (AC-45, D19).** The first R2 plan has been applied and the user has looked at the result (see "Sign-off of AC-45"). | The user | The filled sign-off table. | Open (starts when the first R2 plan is applied) |
| 7 | The user approves R2 for production explicitly. Phase 9 is not started before this. | The user | Their written approval in the pull request or the review record, with the date. | Not given |

## Sign-off of AC-45

To be filled in by the user after the first R2 plan has been applied. This is a user acceptance, not an automated test.

AC-45 sign-off: the 36 first-run mails under "Other" and the mails flagged on 2026-11-08 are where I want them. Signed: ______ Date: ______

| Field | Value |
| --- | --- |
| Date the first R2 plan was applied | |
| Mails the plan moved | |
| The 36 first-run mails under "Other" are where the user wants them (yes or no) | |
| The mails flagged on 2026-11-08 are where the user wants them (yes or no) | |
| Mails the user moved back or re-filed, and why | |
| Accepted by the user (yes or no, date) | |
