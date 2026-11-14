---
intent: INT-002
feature: web-settings
---

# U-web-settings-46: Reset to defaults: web (R2)

- Layer: web
- Contract: the secondary button "Reset to defaults", kept apart from Save, opens `ConfirmDialog` (native `<dialog>` with `showModal`) that names the values including the time zone; the destructive button reads "Replace my settings with defaults", initial focus is "Keep my settings"; on confirm the page calls `POST /api/settings/reset`, shows the saving state and the banner "Defaults restored. The Undo button is in the Telegram message." The form renders the button through a slot file `ResetSlot.tsx` that U-32 left empty.
- Files: `apps/web/src/components/ConfirmDialog.tsx`, `apps/web/src/features/settings/ResetSlot.tsx`, `apps/web/src/features/settings/Reset.test.tsx`, `apps/web/e2e/ui-states.spec.ts`
- Depends on: U-web-settings-32, U-web-settings-45
- Parallel: no
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl, guardrail-playwright
- Criteria:
  1. Given the dialog opens, When rendered, Then it lists "Time zone Europe/Amsterdam, quiet hours 23:00 to 07:00, daily overview 18:00, reminders 09:00", says the time zone is reset too, and initial focus is "Keep my settings" (AC-25) (type: a11y; level: component).
  2. Given the dialog, When Escape or "Keep my settings" is used, Then it closes, nothing is sent and focus returns to the Reset button (AC-25) (type: happy; level: component).
  3. Given the dialog open, When Tab is pressed repeatedly, Then focus stays inside and the page behind is inert (AC-23) (type: a11y; level: component).
  4. Given confirm, When pressed, Then Save and Reset are disabled, one `POST /api/settings/reset` with the version is sent, and the banner shows (AC-25) (type: happy; level: component).
  5. Given a 409 on reset, When received, Then the conflict banner of U-35 shows and nothing is replaced (AC-11) (type: edge; level: component).
  6. Given the two dialog buttons in greyscale, When rendered, Then the destructive one differs by label, border and weight, not by colour alone (ADR-0035) (type: a11y; level: playwright).
  7. Given the dialog at 320, 375, 768 and 1280 px and 200 % text, When rendered, Then no horizontal scroll and axe finds no violation; the Reset button stacks below Save at 320 px (AC-22) (type: a11y; level: playwright).
