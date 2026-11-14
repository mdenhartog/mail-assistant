---
intent: INT-002
feature: web-settings
---

# U-web-settings-35: Conflict handling: Use mine and Keep Telegram's (R1)

- Layer: web
- Contract: rebuild of `ConflictLayer.tsx`: on 409 the form takes the returned `Settings`, shows the info banner (`role="alert"`, focus moves to it, "Nothing is saved until you press Save again.") and marks every field Marco had edited with his own value and two toggle buttons "Use mine" and "Keep Telegram's"; nothing is saved until Save is pressed again with the new version.
- Files: `apps/web/src/features/settings/ConflictLayer.tsx`, `apps/web/src/features/settings/ConflictBanner.tsx`, `apps/web/src/features/settings/useConflict.ts`, `apps/web/src/features/settings/Conflict.test.tsx`
- Depends on: U-web-settings-32
- Parallel: yes (with U-33, U-34)
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the page at version 1 and a 409 with version 2, When shown, Then the banner "Settings changed in Telegram at 14:02 (Amsterdam time). I loaded the new values." has `role="alert"` and focus, and the fields show the new values (AC-11) (type: happy; level: component).
  2. Given Marco edited quiet start to 22:30 and Telegram has 23:00, When shown, Then that field says "You typed 22:30, Telegram now has 23:00" with "Use mine" and "Keep Telegram's"; unedited fields have no mark (AC-28) (type: happy; level: component).
  3. Given "Use mine", When pressed, Then the field holds 22:30 again as an unsaved edit (AC-28) (type: happy; level: component).
  4. Given "Keep Telegram's", When pressed, Then the mark is gone and the field holds 23:00 (AC-28) (type: happy; level: component).
  5. Given the conflict and no button or Save pressed, When time passes, Then nothing is sent; Save afterwards sends the new version (AC-11) (type: edge; level: component).
  6. Given the other change came from the web in another tab, When shown, Then the banner says "from the web" (type: edge; level: component).
  7. Given a second 409 while resolving, When it arrives, Then the banner and marks are recomputed against the newest values (type: edge; level: component).
  8. Given the buttons, When read by a screen reader, Then each is named with its field ("Use mine for Quiet hours") and axe finds no violation (AC-23) (type: a11y; level: component).
