---
intent: INT-002
feature: web-settings
---

# U-web-settings-05: HTTP surface: errors, headers, request id, LimitGuard seam, route inventory (R1)

- Layer: backend
- Contract: `application/problem+json` handlers for 400 (one body), 401, 403 (one body for CSRF, Origin and a write without session), 404, 405, 413, 415, 429 (`Retry-After`) and 500, all with a generic title; middleware adds `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` to every response and the CSP (`script-src 'self'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`) to HTML; request id from `IdSource`, returned as `X-Request-Id`, a client value never accepted; `/docs`, `/redoc`, `/openapi.json` off in production; `LimitGuard` (`async check(bucket, request)`, default no-op) is a FastAPI dependency that routes declare and U-24 replaces by a real implementation; the route inventory test allows exactly the design's paths (R1: `/auth/request-code`, `/auth/verify-code`, `/auth/logout`, `/api/session`, `/api/settings`, `/api/places`, plus the probes) and every route declares `public` or `session`.
- Files: `backend/app/main.py`, `backend/app/errors.py`, `backend/app/middleware.py`, `backend/app/limit_guard.py`, `backend/app/core/security.py`, `backend/tests/test_route_inventory.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-04
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given an unhandled exception that carries a canary, When the response is built, Then the body is a generic 500 problem without class, message or trace, and the canary is only in the server-side error log as the class name (AC-15, W-6) (type: security; level: api).
  2. Given an unknown path, When requested, Then 404 with a generic problem (AC-15) (type: error; level: api).
  3. Given any response (200, 400, 401, 404, 429), When inspected, Then `no-store`, `nosniff` and `no-referrer` are present (AC-14, W-5) (type: security; level: api).
  4. Given an HTML response the api serves, When inspected, Then the CSP has exactly the four directives and no `unsafe-inline` (AC-14, W-5) (type: security; level: api). Superseded by U-59: one deny-all CSP (`default-src 'none'; frame-ancestors 'none'`) on every API response.
  5. Given a request with `X-Request-Id: attacker`, When answered, Then the response header is the id from `IdSource` (W-13) (type: security; level: api).
  6. Given production settings, When `/docs`, `/redoc` and `/openapi.json` are requested, Then 404 each (AC-19, W-6) (type: security; level: api).
  7. Given a route outside the allow-list, a route without a `public` or `session` marker, and a `POST` write without the csrf marker, When the inventory runs, Then each fails naming the path (AC-15; flipped by U-45: `/api/settings/reset` is on the allow-list since R2) (type: security; level: unit).
  8. Given a route with the default `LimitGuard`, When called, Then it passes; Given a guard that raises, Then the response is the 429 problem with an integer `Retry-After` and the body names no limit or client (type: edge; level: api).
  9. Given `uv run python -m app.export_openapi --check`, When run, Then it passes and every exported path is on the allow-list (AC-15) (type: happy; level: ci).
