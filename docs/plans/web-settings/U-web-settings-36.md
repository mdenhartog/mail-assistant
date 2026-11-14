---
intent: INT-002
feature: web-settings
---

# U-web-settings-36: Accessibility and responsive states: Playwright ui-states (R1; release gate)

- Layer: web
- Contract: a Playwright project `ui-states` with a stubbed API (`route.fulfill`, no backend) that renders every state of the login page (step 1, sending, step 2, wrong code, expired code, too many tries, cooldown, hourly cap, session expired), the settings page (loading, loaded, dirty, saving, saved, validation error, save failed, conflict, session expired) and the not-found and refused (403) pages, at 320, 375, 768 and 1280 px, in light and dark, and at 200 % text size. This is the only place for pixel, contrast and overflow checks (AC-22, AC-23).
- Files: `apps/web/e2e/ui-states.spec.ts`, `apps/web/e2e/support/stubs.ts`, `apps/web/playwright.config.ts`
- Depends on: U-web-settings-30, U-web-settings-31, U-web-settings-32, U-web-settings-33, U-web-settings-34, U-web-settings-35
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y
- Criteria:
  1. Given every state at every viewport, When measured, Then `scrollWidth` is at most `clientWidth` (AC-22) (type: a11y; level: playwright).
  2. Given every state at every viewport in light and dark, When axe runs with contrast on, Then no violation (AC-22) (type: a11y; level: playwright).
  3. Given text at 200 % size, When rendered, Then nothing is clipped or overlaps, and the buttons stack with the primary one first at 320 px (AC-22) (type: edge; level: playwright).
  4. Given the keyboard only, When the stubbed login-to-saved flow runs, Then every step is reachable, and on submit with an invalid field focus lands on the first invalid field (AC-23) (type: a11y; level: playwright).
  5. Given each interactive element, When focused, Then the outline has a computed non-zero width and the token colour (AC-23) (type: a11y; level: playwright).
  6. Given every target, When measured, Then at least 24 px on any viewport and at least 44 px on the touch viewports, with 8 px between neighbours (AC-23) (type: a11y; level: playwright).
  7. Given a slow stubbed save, When pending, Then Save is disabled and a second click sends no second request (AC-23, W-12) (type: edge; level: playwright).
  8. Given `prefers-reduced-motion: reduce`, When rendered, Then computed animation and transition durations are 0 (AC-23) (type: a11y; level: playwright).
  9. Given the `ui-states` project, When run in CI, Then it needs no backend and runs in the `web` job (type: happy; level: ci).
