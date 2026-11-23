---
intent: INT-008
feature: label-structure
---

# U-label-structure-26: Web: Review moves with pairs, full names and tips (R2)

- Component: web
- Layer: web
- Contract: Review moves shows the full nested names and the pair (topic, extra), and for every category with items below the threshold its tip as plain text, labelled as a suggestion ("nothing was changed") with a link to that category's edit view; the page says which items were already moved on their own; the existing approve and reject controls keep working.
- Files: `apps/web/src/pages/review/`, `apps/web/src/api/categories/plan.queries.ts`, tests
- Depends on: U-label-structure-39
- Parallel: yes
- Guardrails: guardrail-react, guardrail-typescript, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given items with nested names and a pair, When the page renders, Then it shows the full names and the pair. (type: happy)
  2. Given a category with a tip, When shown, Then the tip is plain text with the words "suggestion, nothing was changed" and a link to the category's edit view. (type: happy)
  3. Given a tip with markup or a link in its text, When shown, Then it is plain text, not a link. (type: security)
  4. Given a category without items below the threshold, Then no tip is shown. (type: edge)
  5. Given the page, When axe runs in three viewports, Then it finds no violations. (type: a11y)
