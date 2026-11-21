---
id: ADR-0056
title: "Re-sort on request: a typed confidence threshold, two plans and system approval"
status: accepted
area: architecture
tags: [label-structure, mail-triage, postgresql, plans, security]
date: 2026-11-21
supersedes: ADR-0046 (decisions 1 to 4; decisions 5 to 8 stay)
guardrails: [guardrail-sqlalchemy-alembic, guardrail-python, guardrail-gmail, guardrail-telegram]
---

## Context

ADR-0046 builds a plan automatically after a list change (debounce) and at the first start, and approval is plan-level (`ready -> scheduled`, pending items become rejections). INT-008 reverses D4: a list change never moves old mail (D8, D12); the user presses "Sort everything again" and types a confidence threshold (D9); sure items move after a delay without review, the rest is reviewed. A plan that is partly approved by the system does not fit plan-level approval (round table, architect).

## Decision

1. **Request.** The api calls the `SECURITY DEFINER` function `request_resort(mailbox_id, confidence_threshold)`, which writes an insert-only `resort_request` row (threshold a whole number from 50 to 100, actor digest and channel derived by the database). No automatic plan exists: the debounce build and the first-start plan of ADR-0046 are removed (D12). The field shows the threshold of the latest request (it starts at 50).
2. **Two plans.** For one request the agent builds two plans from the same scan: a plan of kind `auto` (items with `confidence_pct >= threshold` and all sender-rule items) and a plan of kind `review` (the rest). The one-non-terminal-plan rule is per mailbox **and kind**. The plan copies the threshold from its request, so it cannot change under a running plan.
3. **System approval.** The agent approves the `auto` plan only through its own `SECURITY DEFINER` function `approve_system_plan(plan_id)`: it locks the plan, re-checks every item's confidence against the stored threshold (sender-rule items are confidence 100 and verified, D17), records the decision source `threshold`, inserts a `plan_approval` (counts toward the rolling 24-hour wait of ADR-0047) and sets `scheduled` with `apply_after` by the rule of D16 of `mail-categories`. The api role has no right on this function (SQLSTATE 42501). The `review` plan is approved by the user through `approve_plan` as before.
4. **Pair targets.** A plan item holds the old and the new pair (`old_topic_id`, `old_extra_id`, `new_topic_id`, `new_extra_id`) and `confidence_pct`; an item exists when the pair would change (D13). A mail with a topic and an extra label is no longer "unclear".
5. **Cancel.** Cancel, Undo and Lock on a sort-again notice cancel the plan. An upload or rename that removes a category an open plan targets cancels that plan (D20). A list save while a plan is `scheduled` or `applying` lets it finish; a pending `review` plan is replaced.
6. **Tips.** When the `review` plan is ready, the agent makes one model call per category with items below the threshold (budget share above the reserve), from the category, its description and the items' sender and subject (never the body). A tip is plain text, capped, may only suggest a sender that is the authenticated domain of at least 3 such items and is not on a refused list, and is stored with the plan items and deleted with them. Tips are never applied.

## Consequences

- Supersedes decisions 1 to 4 of ADR-0046 (state machine owned by the agent, approval, build trigger, apply); decisions 5 (Move back), 6 (Gmail operations), 7 (Telegram exception) and 8 (pinned mail) stay.
- Extends ADR-0047 with an agent-only function and the decision source `threshold`.
- Rebuild of `core/resort_plan.py`, `usecases/resort_build.py` and the plan tables (`plan.kind`, `plan.request_id`, `plan.threshold`, the item pair and confidence), not a flag.
- Accepted risk AR-2: the model's confidence is self-reported. The delayed apply with Cancel, Move back for every item, the minimum threshold of 50 and the code-side rule bound the harm to a wrong label.
- A stolen session can press the button; sender-rule items then move without review after the delay (D17, accepted). The Telegram notice with Cancel and Lock is the control.

## Alternatives

- One plan with item-level apply batches: keeps one state machine but mixes two approval sources in one frozen plan. Rejected on the architect's advice.
- Store the threshold as a web setting (ADR-0023): races the build and adds a table without `mailbox_id`. Rejected.
- Let the api approve system items: the api would hold the power to bypass review. Rejected.
