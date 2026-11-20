---
id: ADR-0046
title: "Re-sort plans: lifecycle, Gmail operations, delayed apply and the Telegram exception to D1"
status: accepted
area: architecture
tags: [mail-categories, mail-triage, gmail, telegram, budget]
date: 2026-11-14
revised: 2026-11-14
guardrails: [guardrail-gmail, guardrail-telegram, guardrail-python]
---

## Context

D4, D5, D8 to D10 and D14 to D18 of `mail-categories`: a changed list makes a plan, the user approves, and the agent moves mail. The threat model (MC-3, MC-8 to MC-12, MC-19) asks for a reversible, bounded and attributable apply. The phase 3 round table found that approvals had no commit point and that the plan states differed between documents.

## Decision

1. **State machine, owned by the agent** (`core/resort_plan.py`, compare-and-set under `FOR UPDATE`). Plan states: `building, ready, scheduled, applying, applied, replaced, discarded, cancelled`. Item states: `pending, approved, rejected, applied, skipped, failed`. `scheduled` is always used: below the threshold `apply_after` is now. One non-terminal plan per mailbox (partial unique index).
2. **Approvals are database functions** (ADR-0047): `record_decision` sets decisions and writes an append-only record; `approve_plan` records the approval, turns still-pending items into rejections, counts the approvals of the mailbox over 24 hours and sets `scheduled` with `apply_after`. The api has no `UPDATE` on plan tables. Decisions are frozen from `scheduled`.
3. **Build** starts when the list has been stable for the debounce time (default 10 minutes), and at the first R2 start when no plan exists; one build at a time, a newer list cancels it; it judges mail in scope within the budget above the reserve of ADR-0021 and continues over days; the cap is 5 000 mails, newest first, the rest reported as "not looked at" (D15).
4. **Apply**: the agent takes `scheduled` plans whose `apply_after` has passed. Approvals above the threshold (counted over 24 hours, set by deployment configuration only) wait 15 minutes with a Telegram notice offering Cancel and Lock web sign-in (D16). A list change while a plan is `scheduled` or `applying` lets that plan finish, and the next build starts only after it is terminal (one non-terminal plan per mailbox); a plan in `building` or `ready` is replaced. The threshold and the delay are read from the table `apply_config`, which only the agent writes from its deployment configuration; the 24-hour sum counts approved items including the current approval and waits when it is strictly above the threshold. Before each move the agent checks the mail is still in scope, carries the old label and is not pinned; it removes the old `Assistant/` label and adds the new one; a retry after a Gmail success and a database failure ends as applied. Lock cancels `scheduled` plans.
5. **Move back**: the apply audit keeps message id, old and new label, channel and actor digest (one year, no sender or subject). A Telegram button or `POST /api/plan/{id}/move-back` (an insert-only request) makes the agent restore them, skipping mail changed meanwhile. Restoring a label that is no longer in the list is the one exception to the list check of apply.
6. **Gmail operations** in a narrow adapter `adapters/gmail_resort.py`: list, read, add label, remove label, create label, rename an `Assistant/` label by id. No label delete, trash, spam, delete message or send (D18); a reflection test against an allow-list enforces it. The scope stays `gmail.modify`.
7. **Telegram exception to D1** (D17): Undo, Cancel, Move back and Lock are allowed in Telegram; they restore or stop a change and never edit the list. Each button carries a nonce; only its hash is stored in `telegram_action` with chat id, kind, target and expiry, consumed once by compare-and-set; a late or repeated press changes nothing and says so.
8. Pinned mail (ADR-0045) is never a plan item and is re-checked before each apply.

## Consequences

- Extends ADR-0021 (budget share) and ADR-0033 (Telegram notices, lock, nonces).
- The plan page needs build progress, which comes from the plan's cursor.
- R1 has no move-back for mail filed under an undone list (MR-4); R2 adds it.
- `ConfirmDialog` gets a `tone` (safe or danger) so that safe confirmations are not red; this rebuilds a built component, not a flag (rebuild-not-patch).

## Alternatives

- Apply from the api: the api has no Gmail access and must not get it. Rejected.
- Table-level `UPDATE (decision)` with a trigger: races the agent's compare-and-set and has no commit point for the threshold. Rejected.
- Re-authentication for approvals: friction for one user and no help when the mailbox is taken. Kept as a later option (ADR-0033).
- Delete empty labels: a Gmail operation with a race and little value. Rejected (D18).
