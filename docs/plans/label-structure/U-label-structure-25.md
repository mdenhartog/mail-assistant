---
intent: INT-008
feature: label-structure
---

# U-label-structure-25: Web: the sort-again controls and the archive label field (R2)

- Component: web
- Layer: web
- Contract: on the Categories page: a labelled, keyboard-operable threshold field (starts at 50, then shows the latest request) with the text "Mail from a sender rule always moves. Everything else the model is at least <x> % sure of moves by itself after a short delay, and each can be undone with Move back." and under the button "Nothing moves until a short delay; you can cancel in Telegram."; the button "Sort everything again" (disabled with the reason while a plan is open); the archive label field with its sentence; hooks for the request routes.
- Files: `apps/web/src/pages/categories/sort-again/`, `apps/web/src/pages/categories/ArchiveLabelField.tsx`, `apps/web/src/api/categories/resort.queries.ts`, tests
- Depends on: U-label-structure-19, U-label-structure-21
- Parallel: yes
- Guardrails: guardrail-react, guardrail-typescript, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the first visit, When the page renders, Then the threshold field shows 50; Given a later visit, Then it shows the latest request. (type: happy)
  2. Given 49, 50.5, "50 ", "abc" or over 100, When the user presses the button, Then the field shows the reason and no request is made; 50 and 100 are accepted. (type: error)
  3. Given an open plan, When the page renders, Then the button is disabled with the reason. (type: edge)
  4. Given the texts of the spec, When shown, Then they match word for word. (type: happy)
  5. Given the archive label field, When a valid name is saved, Then it is sent; a refused name shows the reason from the api. (type: happy)
  6. Given the field and the button, When used by keyboard and read by a screen reader, Then they are labelled and errors are linked with `aria-describedby` and receive focus. (type: a11y)
