---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-13: Web: the rename preview, restore, recently deleted and the first-run empty state

- Component: web
- Layer: web
- Contract: A page section shows the rename preview as cards (a summary "N labels, M mails", sort by count, a skip per label), a typed confirmation, the result with the notice that Gmail apps may show old names for a while, a Restore button, the "recently deleted" list, and the first-run empty state ("load your YAML first; the list is no longer read from Gmail").
- Files: `apps/web/src/features/categories/rename/RenamePreview.tsx`, `apps/web/src/features/categories/rename/RecentlyDeleted.tsx`, `apps/web/src/api/categories/rename.api.ts`, `apps/web/src/api/categories/rename.queries.ts`, tests beside them
- Depends on: U-label-prefix-removal-11
- Parallel: yes
- Guardrails: guardrail-react, guardrail-typescript, guardrail-tanstack-query, guardrail-tailwind, guardrail-vitest-rtl, guardrail-a11y
- Criteria:
  1. Given a pending plan, When the page loads, Then the cards, the summary and a skip per label are shown (AC 4). (type: happy)
  2. Given a merge item, When shown, Then it says "merge N mails into an existing label" (AC 20). (type: happy)
  3. Given the confirmation, When pressed, Then the plan hash and the skipped ids are sent once, and a second click sends nothing. (type: edge)
  4. Given a finished rename, When shown, Then Restore, the stale-name notice and the result are visible and the focus moves to the result (AC 17, 27). (type: a11y)
  5. Given recently deleted labels, When listed, Then names and dates are shown and nothing is editable (AC 29). (type: happy)
  6. Given no list yet, When the page loads, Then the first-run empty state explains the YAML upload. (type: edge)
  7. Given an expired session while the preview is open, When confirming, Then a re-login is asked and the state is kept. (type: error)
  8. Given 375 px, the tab order, `role=alertdialog` for the confirmation and axe on three viewports, When tested, Then there are no violations (AC 17). (type: a11y)
