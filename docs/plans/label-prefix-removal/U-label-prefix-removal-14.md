---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-14: End-to-end journey: preview, confirm, merge, wait and delete

- Component: web
- Layer: web
- Contract: A Playwright journey on the prod-like stack that seeds the label state through SQL: the rename preview, the confirmation, the merge into an existing label, a delete after an injected short wait, and the recently deleted list.
- Files: `apps/web/e2e/label-prefix-removal.spec.ts`, `apps/web/e2e/support/labelRename.ts`, `apps/web/playwright.config.ts`
- Depends on: U-label-prefix-removal-06, U-label-prefix-removal-09, U-label-prefix-removal-12, U-label-prefix-removal-13
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y
- Criteria:
  1. Given a seeded rename plan, When the user previews and confirms, Then the page shows the result (AC 4, 5). (type: happy)
  2. Given a merge item, When confirmed, Then the page shows the merge and the old label is empty afterwards (AC 20). (type: happy)
  3. Given an empty label past its injected wait, When the agent cycle runs, Then it is listed under recently deleted (AC 7, 29). (type: happy)
  4. Given the whole journey, When run on three viewports, Then axe finds no violations (AC 17). (type: a11y)
