---
intent: INT-008
feature: label-structure
---

# U-label-structure-23: Two plans, system approval, apply and cancel (R2)

- Component: mail-triage
- Layer: backend
- Contract: at the end of a build the items are split into an `auto` plan (confidence_pct at or above the stored threshold, and all sender-rule items) and a `review` plan; the agent calls `approve_system_plan` for the `auto` plan; the apply, the delayed apply, the Telegram notice with the numbers (moves on its own, waits for review) and Cancel, "Move back" and "Lock web sign-in", and Cancel, Undo and Lock on a sort-again notice cancel the plan; an upload or rename that removes a target category cancels the open plan; a list save while a plan is `scheduled` or `applying` lets it finish and a pending `review` plan is replaced; one non-terminal plan per mailbox and kind.
- Files: `agents/mail-triage/app/usecases/resort_build.py`, `agents/mail-triage/app/usecases/resort_apply.py`, `agents/mail-triage/app/core/resort_plan.py`, `agents/mail-triage/app/usecases/plan_notice.py`, tests
- Depends on: U-label-structure-20, U-label-structure-22
- Parallel: no
- Guardrails: guardrail-python, guardrail-gmail, guardrail-telegram, guardrail-pytest
- Criteria:
  1. Given items of confidence 95, 80 and 79 and a threshold of 80, When the plans are made, Then the first two are in the `auto` plan and the third in the `review` plan; at 96 only sender-rule items qualify; at 100 only confidence 100; "at or above". (type: edge)
  2. Given an approved `auto` plan, When the delay has not passed, Then nothing moves; After it, Then the items move, and the notice names the numbers and offers Cancel, "Move back" and "Lock web sign-in" with a line saying what Lock does. (type: happy)
  3. Given a Cancel, Undo or Lock before the apply, When pressed, Then nothing of the plan moves and it is cancelled. (type: security)
  4. Given the user moved a mail meanwhile, When the item is applied, Then it is skipped and shown as skipped. (type: edge)
  5. Given items below the threshold, When the `review` plan is ready, Then none moves before the user approves it; a new request replaces the pending `review` plan. (type: happy)
  6. Given an open plan and an upload or rename that removes its target, When it happens, Then the plan is cancelled and no item is applied to a deleted label; a list save while `scheduled` or `applying` lets the plan finish. (type: edge)
  7. Given system approvals, When counted, Then they count toward the rolling 24-hour wait of D16. (type: edge)
