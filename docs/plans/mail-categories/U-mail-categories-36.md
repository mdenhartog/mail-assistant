---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-36: Filter and sort controls on the Review moves page

- Component: web
- Layer: web
- Release: R2
- Contract: a labelled sender search and a sort choice above the items of a group; both call the items route of U-35; a result count is shown before "select all" is offered for the matching mails; an empty result has its own text; the loading, error and empty states are covered.
- Files: apps/web/src/features/review/**, apps/web/src/api/**, apps/web/e2e/review.spec.ts
- Depends on: U-mail-categories-35
- Parallel: no
- Guardrails: guardrail-react, guardrail-typescript, guardrail-tanstack-query, guardrail-vitest-rtl, guardrail-a11y, guardrail-tailwind, guardrail-playwright
- Criteria:
  1. Given a group with mails from several senders, When the user types a sender, Then only the matching mails show (type: happy)
  2. Given a sort choice, Then the mails show in that order (type: happy)
  3. Given a filter, When the user selects all, Then the count of matching mails is named first and only they are selected (type: edge)
  4. Given no match, Then an empty text shows (type: edge)
  5. Given the keyboard only, Then the search and the sort are reachable and labelled, and axe finds nothing at 4 widths (type: a11y)
  6. Given the sender text, Then it is never put in the URL, browser storage or a log (type: security)
