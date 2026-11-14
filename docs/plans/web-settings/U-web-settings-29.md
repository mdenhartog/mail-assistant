---
intent: INT-002
feature: web-settings
---

# U-web-settings-29: UI primitives: Button, Field, Banner, TimeField, Layout (R1)

- Layer: web
- Contract: presentation components from the screens document, tokens only: `Button` (primary, secondary, ghost, danger; `loading`, `disabled`), `Field` (label, hint, error, ids by `useId`), `Banner` (danger, success, info; title, text, optional action), `TimeField` (native `input type=time` step 60, the 24-hour text beside it, stepped 15-minute select fallback), `Layout` (skip link, header with Sign out, `main`, focus ring from the token).
- Files: `apps/web/src/components/Button.tsx`, `apps/web/src/components/Field.tsx`, `apps/web/src/components/Banner.tsx`, `apps/web/src/components/TimeField.tsx`, `apps/web/src/components/Layout.tsx`
- Depends on: U-web-settings-01
- Parallel: yes (with the backend units)
- Guardrails: guardrail-react, guardrail-tailwind, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given `loading`, When rendered, Then the label changes ("Saving..."), `aria-disabled` is set and a second click calls the handler once in total (AC-23, W-12) (type: edge; level: component).
  2. Given a Field with hint and error, When rendered, Then the label is linked, hint and error are in `aria-describedby`, `aria-invalid` is set only when invalid, the error has `role="alert"` and a visible "!" mark (AC-23) (type: a11y; level: component).
  3. Given the TimeField with a stored `22:10`, When rendered, Then the value is shown unchanged with "= 22:10"; the select fallback offers 15-minute values plus the unrounded stored value (C-7) (type: edge; level: component).
  4. Given Banner kinds, When rendered, Then danger and conflict use `role="alert"`, success and info use `role="status"`, and each has a title element and a non-colour marker (AC-23) (type: a11y; level: component).
  5. Given a Banner re-rendered with the same props, When announced, Then the live region node is kept, not recreated (AC-23) (type: edge; level: component).
  6. Given Layout, When tabbed, Then the skip link is first and moves focus to `main` (AC-23) (type: a11y; level: component).
  7. Given every component in every state, When axe runs (contrast off in jsdom), Then no violation (AC-22) (type: a11y; level: component).
  8. Given `prefers-reduced-motion`, When set, Then the component sets no transition (AC-23) (type: a11y; level: component).
