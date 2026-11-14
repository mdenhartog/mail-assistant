---
intent: INT-002
feature: web-settings
---

# U-web-settings-28: Web app shell, API client and session (R1)

- Layer: web
- Contract: React Router routes `/`, `/login`, `/settings` (anything else is a not-found page); TanStack Query client; the typed client generated from `docs/api/openapi.json` (`pnpm --filter web gen:api`, checked in CI); `useSession()` calls `GET /api/session` and keeps the CSRF token in memory only; `apiFetch` adds `X-CSRF-Token` to writes only; a 401 on any request, also a background refetch, goes to `/login?notice=expired`; a 403 shows the full-page "This request was not allowed." with "Back to sign in" and no settings data in the DOM; page titles per screen, `lang="en"`; the Vitest coverage threshold of 90.
- Files: `apps/web/src/main.tsx`, `apps/web/src/App.tsx`, `apps/web/src/api/client.ts`, `apps/web/src/api/schema.d.ts` (generated), `apps/web/src/session/useSession.ts`, `apps/web/src/pages/AccessRefused.tsx`, `apps/web/vite.config.ts`
- Depends on: U-web-settings-01, U-web-settings-20
- Parallel: no
- Guardrails: guardrail-react, guardrail-react-router, guardrail-tanstack-query, guardrail-vite, guardrail-typescript, guardrail-vitest-rtl
- Criteria:
  1. Given `GET /api/session` answers 401, When `/settings` is opened, Then the app shows `/login` (AC-2) (type: security; level: component).
  2. Given a valid session, When `/login` is opened, Then the app shows `/settings` (type: happy; level: component).
  3. Given a session, When the app runs, Then the CSRF token is in memory only: not in `localStorage`, `sessionStorage`, cookies or any URL (AC-8, W-4) (type: security; level: component).
  4. Given a `PUT` and a `GET`, When sent, Then only the write carries `X-CSRF-Token` (type: happy; level: component).
  5. Given a 401 on a write and a 401 on a background refetch of settings, When received, Then each goes to `/login?notice=expired`, nothing is retried (AC-12 first half) (type: happy; level: component).
  6. Given a 403, When received, Then the full-page refusal text and "Back to sign in", and no value of the settings in the DOM (AC-2) (type: security; level: component).
  7. Given "Sign out", When pressed, Then `POST /auth/logout` with the token, then `/login` (AC-7) (type: happy; level: component).
  8. Given `openapi.json` changes, When `gen:api` runs in check mode, Then it fails if `schema.d.ts` is stale (AC-15) (type: error; level: ci).
  9. Given the built `index.html` and CSS, When read, Then no URL outside the same origin is referenced and `lang="en"` is set (D-2, AC-14) (type: security; level: ci).
  10. Given the Vitest config, When read, Then `coverage.thresholds` are 90 and `pnpm -r test` fails below them (type: happy; level: ci).
