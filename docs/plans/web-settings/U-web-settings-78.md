---
intent: INT-002
feature: web-settings
---

# U-web-settings-78: The login page says it wants the username, not the e-mail address (R1; D-22)

- Layer: web
- Contract: under the label of the username field a fixed hint, "Your username, not your e-mail address.", is always visible and linked to the input with `aria-describedby` (the error id stays in the list). The `Field` component takes it through its existing `hint` prop. The text is static, carries no server data, does not say that a name exists (ADR-0038) and changes nothing that is sent to the api or any error behaviour. The code step does not show it.
- Files: `apps/web/src/pages/UsernameStep.tsx`, `apps/web/src/pages/LoginPage.test.tsx`
- Depends on: U-web-settings-31
- Parallel: yes
- Guardrails: guardrail-react, guardrail-vitest-rtl, guardrail-a11y, guardrail-tailwind, guardrail-playwright
- Criteria:
  1. Given the login page, When rendered, Then the hint is visible and the username's accessible description contains it (type: happy; level: component).
  2. Given an empty username sent, When the error shows, Then the description holds both the hint and the error (type: error; level: component).
  3. Given the login states, When checked at 320, 375, 768 and 1280 px, in light and dark and at 200 % text, Then axe finds nothing (type: a11y; level: e2e, ui-states).
  4. Given the rest of the page, When the unit is built, Then the existing tests pass unchanged (type: edge; level: component).
  5. Given the code step, When shown, Then the hint is not on the page (type: edge; level: component).
