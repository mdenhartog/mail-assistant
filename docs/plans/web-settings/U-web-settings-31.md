---
intent: INT-002
feature: web-settings
---

# U-web-settings-31: Login page: resend, countdown and refusal states (R1)

- Layer: web
- Contract: the states of Screen 1 beyond U-30: "Send a new code" disabled for 60 seconds with visible countdown text ("You can ask for a new code in 52 seconds.", `aria-live=off`, with a separate hidden polite status for the start and the end only), "A new code was sent. The earlier code no longer works.", expired code banner with focus on "Send a new code", too many wrong tries (code field disabled until a new code), 429 cooldown from `Retry-After`, 429 hourly cap ("Try again in about 25 minutes."), web lock banner. The countdown uses an injected clock.
- Files: `apps/web/src/pages/ResendControl.tsx`, `apps/web/src/pages/useCountdown.ts`, `apps/web/src/pages/refusals.tsx`, `apps/web/src/pages/CodeStep.tsx`, `apps/web/src/pages/Refusals.test.tsx`
- Depends on: U-web-settings-30
- Parallel: no
- Guardrails: guardrail-react, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given a code sent at t, When the clock is at t+0, t+8 and t+60 s, Then the button is disabled with "in 60 seconds", "in 52 seconds", and enabled with "now"; the hidden polite status announced only at the start and the end (AC-31, AC-23) (type: a11y; level: component).
  2. Given "Send a new code" is pressed after the countdown, When the answer arrives, Then "A new code was sent. The earlier code no longer works.", the code field is cleared and the countdown restarts (AC-5) (type: happy; level: component).
  3. Given a 429 with `Retry-After: 41`, When shown, Then the info banner "Please wait before asking for another code. You can try again in 41 seconds." and the same countdown rule (AC-31) (type: error; level: component).
  4. Given a 429 with a long `Retry-After` from the hourly cap, When shown, Then the `role="alert"` banner "You have asked for too many codes this hour. Try again in about N minutes." with N rounded up, and the button stays disabled until then (AC-31, W-7) (type: error; level: component).
  5. Given the expired-code case (a 400 after more than 10 minutes by the injected clock), When shown, Then "This code has expired. Send yourself a new one." with focus on "Send a new code" and the code field cleared (AC-3) (type: error; level: component).
  6. Given `attemptsLeft: 0` or a dead request, When shown, Then "Too many wrong tries. This code no longer works. Send a new code." and the code field disabled until a new code is sent (AC-5) (type: error; level: component).
  7. Given the verify answer for a locked web (identical to the generic 400, U-18), When the page shows it, Then it shows exactly the generic refusal text and no mention of a lock; the page has no locked state (AC-27, W-1) (type: security; level: component).
  8. Given `prefers-reduced-motion`, When the countdown runs, Then the countdown is text only (AC-23) (type: a11y; level: component).
  9. Given axe on each state, When run, Then no violation (AC-22) (type: a11y; level: component).
