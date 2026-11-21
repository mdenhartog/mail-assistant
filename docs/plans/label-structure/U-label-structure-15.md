---
intent: INT-008
feature: label-structure
---

# U-label-structure-15: Web: the Categories list and the edit view (R1)

- Component: web
- Layer: web
- Contract: the Categories page (English): a collapsed list with one row per category (indented name, kind chip, sender count, tick), collapsible parents, a search field and the filter "Always notify only", 44 px targets, a full-screen edit view with Save and Cancel, help texts per field, a sender textarea (one entry per line, live count, per-line errors, conflict message), the fixed explanation block, empty, unsaved-change and error states; hooks in `src/api/categories/*.queries.ts` with types from OpenAPI.
- Files: `apps/web/src/pages/categories/`, `apps/web/src/api/categories/`, `apps/web/src/components/` (new pieces), tests
- Depends on: U-label-structure-11
- Parallel: yes
- Guardrails: guardrail-react, guardrail-typescript, guardrail-tanstack-query, guardrail-tailwind, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given 43 nested categories on a 360 px screen, When the page renders, Then it is a collapsed list with search and the filter, tap targets of at least 44 px and no horizontal scroll at 200 % zoom. (type: a11y)
  2. Given a row, When tapped, Then a full-screen edit view opens with Save and Cancel and no inline sender editor. (type: happy)
  3. Given the sender textarea, When the user types, Then it shows a live count ("37 of 100"), per-line errors and a conflict message that names the other category. (type: happy)
  4. Given the fixed block and the help texts, When the page renders, Then they are shown with the wording of the spec. (type: happy)
  5. Given a loading, empty, error and unsaved-change state, When each occurs, Then it is shown and the unsaved-change warning appears on leaving. (type: edge)
  6. Given the tick, When read by a screen reader, Then it is labelled "Always notify, <full category name>" and the tree has nested list semantics. (type: a11y)
  7. Given a description with markup or script text, When shown, Then it is plain text. (type: security)
