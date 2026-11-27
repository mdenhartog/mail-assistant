---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-12: Web: "Review moves" shows the part and why a plan waits

- Component: web
- Layer: web
- Contract: The generated client is regenerated from the OpenAPI of U-11. `features/review/PlanStates.tsx` shows the part number, the checked count over the whole series and one plain sentence per pause reason (`budget`: "paused: the daily budget is used, continues tomorrow"; `pace`; `waiting_for_part`; `cursor_lost`; `expired`; `ended`). It never claims progress while paused. The status is plain text announced politely (`role="status"`). The "Sort again" form shows the plain message of the 409. Colours only through tokens; no arbitrary Tailwind values.
- Files: `apps/web/src/api/schema.d.ts`, `apps/web/src/features/review/PlanStates.tsx`, `apps/web/src/features/review/copy.ts`, `apps/web/src/features/categories/sort-again/SortAgainSection.tsx`, tests next to them
- Depends on: U-daily-budget-partial-plan-11
- Parallel: yes
- Guardrails: guardrail-typescript, guardrail-react, guardrail-tanstack-query, guardrail-tailwind, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the plan waits for the budget, When "Review moves" opens, Then it says "paused: the daily budget is used, continues tomorrow", shows the checked count and shows no progress claim (AC 11). (type: a11y)
  2. Given a part, When the totals grow over the days, Then the part number and the checked count over all parts show (AC 12). (type: happy)
  3. Given each pause reason, When it is shown, Then the sentence is plain text and the status is announced politely (AC 11). (type: a11y)
  4. Given part 2 waits for part 1, When the screen opens, Then it says it waits for part 1 (AC 5). (type: edge)
  5. Given the 409 on a new request, When the form is sent, Then a plain message shows and nothing else changes. (type: error)
  6. Given any state, When axe runs, Then there is no violation in light and dark. (type: a11y)
  7. Given the source, When the token scan runs, Then there is no arbitrary value. (type: edge)
