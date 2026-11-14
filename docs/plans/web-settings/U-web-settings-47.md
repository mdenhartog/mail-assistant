---
intent: INT-002
feature: web-settings
---

# U-web-settings-47: Typed values kept across session expiry (R2)

- Layer: web
- Contract: when a save is answered with 401, the typed values are kept and restored after sign-in at `/settings`, with the banner "Welcome back. Your unsaved changes are restored. Check them and save."; never saved automatically. The draft is held in `sessionStorage` (D-6), tab-scoped, values and version only, removed after 12 hours by the injected clock. The login page then says "Your session ended. Sign in again; what you typed is kept." only when a draft exists.
- Files: `apps/web/src/features/settings/useDraft.ts`, `apps/web/src/features/settings/DraftBanner.tsx`, `apps/web/src/pages/LoginPage.tsx`, `apps/web/src/features/settings/Draft.test.tsx`
- Depends on: U-web-settings-30, U-web-settings-32
- Parallel: yes
- Guardrails: guardrail-react, guardrail-a11y, guardrail-vitest-rtl, guardrail-typescript
- Criteria:
  1. Given a 401 on save with edited fields, When the user signs in again and returns, Then the edited values are restored, the banner shows, and no request was sent for them (AC-12 second half) (type: happy; level: component).
  2. Given the restored draft, When the page loads, Then Save is enabled and nothing is saved until it is pressed (AC-12) (type: edge; level: component).
  3. Given the draft store, When read, Then it holds the five values and the version only, never a token, address or CSRF value (AC-8, W-4) (type: security; level: component).
  4. Given sign-out, a successful save or "Keep Telegram's" for every field, When completed, Then the draft is removed (type: edge; level: component).
  5. Given the stored version is older than the server's after sign-in, When restored, Then the conflict flow of U-35 shows with the draft as Marco's values (AC-11, AC-28) (type: edge; level: component).
  6. Given a draft saved 11 h 59 min and 12 h 00 min ago, When the page loads, Then restored, then discarded (type: edge; level: component).
  7. Given the login page with a draft present and without, When rendered, Then "what you typed is kept" appears only with a draft (type: edge; level: component).
  8. Given axe on the restore banner, When run, Then no violation and the banner is `role="status"` (AC-23) (type: a11y; level: component).
