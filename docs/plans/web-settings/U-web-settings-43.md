---
intent: INT-002
feature: web-settings
---

# U-web-settings-43: Journey over the prod-like stack (R1; release gate)

- Layer: web (end to end)
- Contract: Playwright `journey` against the prod-like stack, one worker, the settings row and the sign-in tables reset by owner SQL between tests; reuses the storage state of U-42.
- Files: `apps/web/e2e/journey.spec.ts`, `apps/web/e2e/support/db.ts`, `apps/web/playwright.config.ts`
- Depends on: U-web-settings-33, U-web-settings-34, U-web-settings-35, U-web-settings-36, U-web-settings-42
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y
- Criteria:
  1. Given a visitor without a session, When `/settings` is opened, Then the login page; `GET /api/settings` gives 401 (AC-2) (type: security; level: playwright).
  2. Given the right code, When signing in, Then the settings page shows values and the last-change line; a wrong code shows the generic error with the tries left and no session cookie (AC-1, AC-3) (type: happy; level: playwright).
  3. Given two concurrent verify requests with the same code in two tabs, When both submit, Then exactly one lands on `/settings` (AC-3) (type: security; level: playwright).
  4. Given two browser contexts on version 1, When context B saves and context A saves afterwards, Then A gets the conflict banner with "Use mine" and "Keep Telegram's" (AC-11, AC-28) (type: edge; level: playwright).
  5. Given the session row is aged by owner SQL, When Save is pressed, and separately when a background refetch runs, Then nothing is stored and the browser goes to `/login?notice=expired`; after signing in `/settings` shows the stored values (AC-12 first half) (type: edge; level: playwright).
  6. Given an injected inline script and an external script, When the page loads, Then a `securitypolicyviolation` event fires, the script does not run, and the CSP header matches (AC-14, W-5) (type: security; level: playwright).
  7. Given `/docs`, `/redoc`, `/openapi.json`, `/healthz`, `/readyz`, `/metrics`, `/api/docs`, `/api/openapi.json`, `/api/readyz` through the edge, When requested, Then 404 each; `GET /api/settings/reset` answers 405 and a `POST` without a session 401 (flipped by U-45); plain HTTP redirects with HSTS (AC-18, AC-19) (type: security; level: playwright).
  8. Given a zone change, When saved, Then the preview, the saved banner with the real notice interval and the last-change line show (AC-28) (type: happy; level: playwright).
  9. Given the sign-in and settings pages at 375 and 1280 px over HTTPS with the real backend, When axe runs, Then no violation (AC-22) (type: a11y; level: playwright).
  10. Given a locked web (the lock row inserted by owner SQL), When the signed-in user calls the API and when a new code is requested and verified, Then 401, and the verify answer is identical in status and body (request id aside) to the answer for a wrong code (AC-27) (type: security; level: playwright).
