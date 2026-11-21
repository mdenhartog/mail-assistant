---
intent: INT-008
feature: label-structure
---

# U-label-structure-24: Tips per category (R2)

- Component: mail-triage
- Layer: backend
- Contract: when a `review` plan is ready the agent makes one model call per category with items below the threshold (budget share above the reserve) from the category, its description and the items' sender and subject (never the body); the tip is plain text, capped; a suggested sender must be the authenticated domain of at least 3 below-threshold items, is shown with its count and is not on a refused list (C-15); the tip is stored on the plan items and deleted with them.
- Files: `agents/mail-triage/app/usecases/plan_tips.py`, `agents/mail-triage/app/adapters/tip_anthropic.py`, `agents/mail-triage/app/core/tips.py`, tests
- Depends on: U-label-structure-23
- Parallel: yes
- Guardrails: guardrail-python, guardrail-llm, guardrail-pytest
- Criteria:
  1. Given a category with items below the threshold, When the plan is ready, Then one tip is stored, as plain text within the cap. (type: happy)
  2. Given a category with no such items, When the plan is ready, Then no tip and no call. (type: edge)
  3. Given a tip suggesting a sender that is not the authenticated domain of at least 3 items, or one on a refused list, When it is checked, Then the suggestion is dropped. (type: security)
  4. Given the tip call, When it is made, Then its input contains no mail body and it counts in the budget above the reserve. (type: security)
  5. Given the plan items are removed (applied, replaced, expired), When it happens, Then their tips are deleted. (type: edge)
  6. Given a tip with markup, a link or an instruction, When stored, Then it is escaped or removed and never applied to the list. (type: security)
