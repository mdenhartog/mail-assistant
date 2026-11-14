---
intent: INT-002
feature: web-settings
---

# U-web-settings-32: Settings form with slots: load, validate, save (R1)

- Layer: web
- Contract: `/settings` with `useSettings()` (query `['settings']`) and a save mutation (`PUT` with `{values, version}`); fields in the order Time zone, Quiet hours (From, Until), Daily overview, Remind-me-later default, each with a hint; states loading, loaded, dirty, saving, validation error (422), save failed. The form composes three slot files that later units replace without editing the form: `ZoneField.tsx` (here a plain text input, rebuilt by U-33), `SaveFeedback.tsx` (here empty, rebuilt by U-34) and `ConflictLayer.tsx` (here empty, rebuilt by U-35). No Reset button in R1.
- Files: `apps/web/src/features/settings/SettingsPage.tsx`, `apps/web/src/features/settings/SettingsForm.tsx`, `apps/web/src/features/settings/useSettings.ts`, `apps/web/src/features/settings/fieldErrors.ts`, `apps/web/src/features/settings/ZoneField.tsx`, `apps/web/src/features/settings/SaveFeedback.tsx`, `apps/web/src/features/settings/ConflictLayer.tsx`
- Depends on: U-web-settings-22, U-web-settings-28, U-web-settings-29
- Parallel: yes (with U-30)
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-tailwind, guardrail-vitest-rtl
- Criteria:
  1. Given the loading state, When rendered, Then skeleton rows, the text "Loading your settings", `aria-busy`, and no Save button yet (AC-22) (type: happy; level: component).
  2. Given loaded settings, When rendered, Then the four fields in order, labelled "Time zone", "Quiet hours" (From, Until), "Daily overview", "Remind-me-later default", each with a hint linked by `aria-describedby` (AC-1, C-11) (type: happy; level: component).
  3. Given nothing changed, When viewed, Then Save is disabled; after an edit it is enabled (type: happy; level: component).
  4. Given Save is pressed, When the request runs, Then the label is "Saving...", Save is `aria-disabled`, inputs are read-only, a polite status says "Saving your settings." and exactly one `PUT` with `{values, version}` and the token is sent even on a double click (AC-9, AC-23, W-12) (type: edge; level: component).
  5. Given a 422 with problems for two fields, When shown, Then each message is next to its field with "!", `aria-invalid`, `aria-describedby` hint plus error, `role="alert"`, and focus moves to the first invalid field in DOM order (AC-10, AC-23) (type: error; level: component).
  6. Given a network error or 5xx, When shown, Then the danger banner "Could not save. Nothing was changed." with "Try again", typed values kept (type: error; level: component).
  7. Given the API returns `<img src=x onerror=alert(1)>` as zone, When rendered, Then it appears as text and no element is created (AC-14, W-5) (type: security; level: component).
  8. Given keyboard only, When the user tabs through, edits, submits invalid, fixes and saves, Then the whole flow works (AC-23) (type: a11y; level: component).
  9. Given the R1 build, When the DOM of the page is searched, Then there is no "Reset" control (R1 exposes no R2 surface; flipped by U-46: since R2 the page has the "Reset to defaults" button and a closed dialog) (type: security; level: component).
  10. Given axe on loading, loaded, dirty, saving, validation error and save-failed states, When run, Then no violation (AC-22) (type: a11y; level: component).
