---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-09: Categories page

- Component: web
- Layer: web
- Release: R1
- Contract: `/categories`: list of category cards (name, description, delete), 'Other', 'Older category' with 'Add to my list', Archive banner, save summary dialog (rename only; replaces review in R2), all states of the brief, data only through `src/api/categories/*.queries.ts`.
- Files: apps/web/src/features/categories/*, apps/web/src/api/categories/*, apps/web/src/router/*
- Depends on: U-mail-categories-04, U-mail-categories-08
- Parallel: no
- Guardrails: guardrail-typescript, guardrail-react, guardrail-vitest-rtl, guardrail-a11y, guardrail-tailwind, guardrail-react-router, guardrail-tanstack-query
- Criteria:
  1. Given the loaded list, Then name, description, counts, 'Other' and the R1 text 'Old mail stays where it is for now.' are shown (AC-1) (type: happy)
  2. Given an invalid field, When saving, Then the error with the mark shows next to the field and focus moves to the first invalid control (AC-2) (type: error)
  3. Given a conflict (409), Then the banner has the focus and the newest list is shown (AC-3) (type: edge)
  4. Given loading, not-ready, save failed, 429, 403 lock and expired session, Then each shows its banner and copy (type: error)
  5. Given an older category, When 'Add to my list' is pressed, Then it is added as a card (AC-53) (type: happy)
  6. Given a name with markup, Then it renders as text (AC-21) (type: security)
  7. Given 320, 375, 768 and 1280 px and 200 % text, Then no horizontal scroll and axe finds nothing (AC-23) (type: a11y)
  8. Given only the keyboard, Then the whole flow works and focus returns sensibly (type: a11y)
