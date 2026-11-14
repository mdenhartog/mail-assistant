---
intent: INT-002
feature: web-settings
---

# U-web-settings-30: Login page: username step and code step (R1)

- Layer: web
- Contract: `/login` (public) with two steps on one page, from the screens document: step 1 heading "Sign in", label "Username" (`autocomplete=username`), button "Send me a code", fine print that a one-time code goes to the address on file and that no mail or calendar access is asked; step 2 heading "Enter your code", "We sent a code to `m***@example.com`. It is valid for 10 minutes.", numeric code field (`inputmode=numeric`, `autocomplete=one-time-code`, `maxlength=6`, spaces removed before sending), "Sign in", "Use another username", and the permanent hint "No code after a few minutes? Ask for a new one after the countdown, or check the mail setup." There is no "could not send" state and no provider button. Uses `POST /auth/request-code` and `POST /auth/verify-code`. The refusal states and resend are in U-31.
- Files: `apps/web/src/pages/LoginPage.tsx`, `apps/web/src/pages/UsernameStep.tsx`, `apps/web/src/pages/CodeStep.tsx`, `apps/web/src/pages/useSignIn.ts`, `apps/web/src/pages/LoginPage.test.tsx`
- Depends on: U-web-settings-28, U-web-settings-29, U-web-settings-17, U-web-settings-18
- Parallel: yes (with U-32)
- Guardrails: guardrail-react, guardrail-react-router, guardrail-tanstack-query, guardrail-a11y, guardrail-tailwind, guardrail-vitest-rtl
- Criteria:
  1. Given `/login`, When rendered, Then `h1` is first in `main`, the username field is the first control, and the fine print names what is asked and says no mail access is requested (AC-24) (type: happy; level: component).
  2. Given the button is pressed, When the request runs, Then it is disabled, reads "Sending...", has `aria-busy`, inputs are read-only and a polite status says "Sending your code." (AC-23) (type: a11y; level: component).
  3. Given the same 200 answer for a known and an unknown username, When step 2 appears, Then focus moves to the code field, the masked address from the answer is shown, and nothing in the page differs between the two cases (AC-24, AC-30) (type: security; level: component).
  4. Given a pasted code `123 456`, When submitted, Then `123456` is posted; letters are not accepted in the field (type: edge; level: component).
  5. Given a right code, When posted, Then the browser goes to `/settings`, whatever `returnTo` the page URL or the answer carries (AC-6) (type: happy; level: component).
  6. Given a 400 with `attemptsLeft: 3`, When shown, Then an inline `role="alert"` linked by `aria-describedby`: "That code is not right. You have 3 tries left." with "!" and border, `aria-invalid`, focus in the selected field (AC-3, AC-23) (type: error; level: component).
  7. Given a 400 without `attemptsLeft`, When shown, Then the same text without a number (AC-3) (type: edge; level: component).
  8. Given `?notice=expired` and any unknown notice such as `<script>`, When rendered, Then the first shows "Your session ended. Sign in again." with `role="status"`, the second renders nothing and nothing from the URL enters the DOM (AC-12 first half, AC-14) (type: security; level: component).
  9. Given the username, code and masked address, When the page is inspected, Then none is stored in `localStorage`, `sessionStorage` or a URL; the code field is cleared after step 2 ends (W-15) (type: security; level: component).
  10. Given axe on step 1, step 2 and the error states, When run, Then no violation; Tab reaches the controls in reading order (AC-23) (type: a11y; level: component).
