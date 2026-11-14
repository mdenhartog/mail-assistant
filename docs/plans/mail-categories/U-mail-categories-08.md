---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-08: Web foundations: dialog tone, navigation, card

- Component: web
- Layer: web
- Release: R1
- Contract: Rebuilt `ConfirmDialog` with `tone` (safe or danger; cancel first, focus trap over all focusable elements, Escape cancels); new `MainNav` (nav with links and `aria-current`, badge text), `Card` moved from `SettingsFields`, `Progress` (`role=progressbar` with value text); `Layout` shows the nav.
- Files: apps/web/src/components/ConfirmDialog.tsx, MainNav.tsx, Card.tsx, Progress.tsx, Layout.tsx and their tests; apps/web/src/features/settings/SettingsFields.tsx (use Card)
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-typescript, guardrail-react, guardrail-vitest-rtl, guardrail-a11y, guardrail-tailwind
- Criteria:
  1. Given tone safe, When the dialog opens, Then the confirm button is the primary style and the cancel button comes first and has the focus (AC-55) (type: a11y)
  2. Given tone danger, Then the confirm button keeps the red style of today (type: happy)
  3. Given a dialog with a link or a checkbox in its body, When Tab and Shift+Tab are pressed, Then the focus turns round over every focusable element (AC-55) (type: a11y)
  4. Given Escape, Then the dialog cancels and never confirms (type: a11y)
  5. Given the nav, Then it is a `nav` with links, `aria-current=page` on the current one and the badge text '842 open items' (type: a11y)
  6. Given Progress with 340 of 2000, Then `role=progressbar` carries the value text (type: a11y)
  7. Given the Settings page, When rendered with the shared Card, Then it looks and tests as before (axe clean) (type: happy)
