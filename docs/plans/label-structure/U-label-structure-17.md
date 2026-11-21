---
intent: INT-008
feature: label-structure
---

# U-label-structure-17: Web: accessibility and end-to-end journey for R1

- Component: web
- Layer: web
- Contract: Playwright journeys in three viewports with axe: upload, preview, confirm, nested page, tick, restore; the R1 documentation page `docs/user-guide/label-structure.md` and the OpenAPI reference are written in phase 8, not here.
- Files: `apps/web/e2e/label-structure.spec.ts`, `apps/web/e2e/support/`
- Depends on: U-label-structure-15, U-label-structure-16
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y, guardrail-typescript
- Criteria:
  1. Given the Categories page in three viewports, When axe runs, Then it finds no violations. (type: a11y)
  2. Given the anonymised golden file, When uploaded, previewed and confirmed, Then the page shows the nested categories with their kinds, senders and ticks. (type: happy)
  3. Given a tick, When set and saved, Then it persists after a reload. (type: happy)
  4. Given 200 % zoom, When the edit view and the preview are used, Then nothing scrolls horizontally. (type: a11y)
  5. Given the keyboard only, When the user uploads, previews and confirms, Then every control is reachable and errors receive focus. (type: a11y)
