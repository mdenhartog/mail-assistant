---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-12: Web: the Label cleanup tile on the Settings page and the two names on the Categories page

- Component: web
- Layer: web
- Contract: The Settings page gains an extra tile "Label cleanup" with an hours-and-minutes field for the waiting time before a delete and a days field for the protection and the retention, saved with the existing settings form (draft, conflict and save feedback as the other tiles); the Categories page gains the two name fields ("Other" and the archive label). Each field shows its default, range and an inline error tied to the field (`aria-describedby`); data only through the `queries` hooks.
- Note: unit 19 changed the OpenAPI document (the upload preview gets a required `adopted` count) and `olderCategories` is now always empty: regenerate `apps/web/src/api/schema.d.ts` (the `gen:api:check` gate), drop `olderCategories` from the web (`OlderCategories.tsx`) and show the adopted count in the upload preview.
- Files: `apps/web/src/features/settings/LabelCleanupTile.tsx`, `apps/web/src/features/settings/SettingsFields.tsx`, `apps/web/src/features/categories/LabelNamesField.tsx`, `apps/web/src/api/categories/labelNames.api.ts`, tests beside them
- Depends on: U-label-prefix-removal-10
- Parallel: yes
- Guardrails: guardrail-react, guardrail-typescript, guardrail-tanstack-query, guardrail-tailwind, guardrail-vitest-rtl, guardrail-a11y
- Criteria:
  1. Given the defaults, When the Settings page loads, Then a tile "Label cleanup" is there and, When it is read, Then each field shows its value, its default and its range. (type: happy)
  2. Given a value outside the range, When saved, Then an inline message is tied to the field and nothing is sent (AC 33). (type: error)
  3. Given the waiting time field, When it is used, Then it is entered as hours and minutes, 12 hours is accepted and 12 hours 1 minute is not. (type: edge)
  4. Given the page is loading, failed or empty, When rendered, Then each state is shown. (type: edge)
  5. Given a keyboard and a screen reader, When the form is used, Then every control has a name and the focus goes to the result message (AC 17). (type: a11y)
  6. Given a 375 px viewport, When rendered, Then nothing scrolls sideways and the targets are 44 px. (type: a11y)
