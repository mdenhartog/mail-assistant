---
intent: INT-002
feature: web-settings
---

# U-web-settings-33: ZoneCombobox with live time (R1)

- Layer: web
- Contract: rebuild of `ZoneField.tsx` as an ARIA 1.2 combobox with list autocomplete: `GET /api/places?q=` (debounced), options "Bangkok, Thailand, UTC+7, 03:42 now" (with "(tomorrow)" or "(yesterday)" when the day differs), the stored value as "Currently: Europe/Amsterdam", a live local-time paragraph computed in the browser with `Intl.DateTimeFormat` from an injected clock; `UTC+7` and `GMT+7` accepted when the lookup supports them; keyboard model and announcements from the screens document.
- Files: `apps/web/src/features/settings/ZoneField.tsx`, `apps/web/src/features/settings/ZoneCombobox.tsx`, `apps/web/src/features/settings/useZoneSearch.ts`, `apps/web/src/features/settings/liveTime.ts`, `apps/web/src/features/settings/ZoneCombobox.test.tsx`
- Depends on: U-web-settings-23, U-web-settings-32
- Parallel: no
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the combobox, When rendered, Then `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete="list"` and `aria-activedescendant` are correct through open and close (AC-23, C-7) (type: a11y; level: component).
  2. Given the user types "bang", When the search resolves, Then options read "Bangkok, Thailand, UTC+7, 03:42 now" and a hidden polite region says "3 places found" (C-7) (type: happy; level: component).
  3. Given the keyboard, When Down, Up, Enter, Escape, a second Escape, Tab, Home and End are used, Then the active option moves with focus staying in the input, Enter selects, Escape closes, the second Escape restores the saved value, Tab accepts nothing unselected (AC-23) (type: a11y; level: component).
  4. Given a chosen zone and a fake clock, When the paragraph updates, Then "In Amsterdam it is 21:42 right now." appears after a 300 ms pause and on selection, inside an `aria-live="polite"` region, correct on both sides of a clock change (AC-28, C-7) (type: happy; level: component).
  5. Given text with no match, When the search returns empty, Then the hint "Nothing found for 'Phuket'. Try the nearest bigger city, or the country." (not `role="alert"`), and an API suggestion is offered (C-7) (type: error; level: component).
  6. Given the field loses focus with unselected text, When blurred, Then the saved value returns; it is never left empty (type: edge; level: component).
  7. Given a place label with markup from the API, When shown, Then it is text only (AC-14) (type: security; level: component).
  8. Given two searches where the first answers late, When both resolve, Then only the latest result is shown (type: edge; level: component).
  9. Given the typed query, When the page is inspected, Then it is in no URL, storage or log (W-15) (type: security; level: component).
  10. Given axe on closed, open, empty and no-result states, When run, Then no violation (AC-22) (type: a11y; level: component).
