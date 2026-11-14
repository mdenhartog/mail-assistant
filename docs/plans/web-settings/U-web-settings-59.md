---
intent: INT-002
feature: web-settings
---

# U-web-settings-59: Safe defaults and response headers (R1; challenge fix; SEC-11, SEC-12, CR-09, CR-11)

- Layer: backend, web (nginx)
- Contract: `environment` defaults to production and `development` or `test` must be set explicitly; the API sends `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-origin` on every response; nginx sends the same security headers in every location from one include; `PUT /api/settings` declares `session` once.
- Files: `backend/app/config.py`, `backend/app/middleware.py`, `backend/app/routers/settings.py`, `apps/web/nginx.conf`, `apps/web/snippets/security-headers.conf`, `backend/tests/test_http_surface.py`, `backend/tests/test_edge_config.py`
- Depends on: U-web-settings-52
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-docker, guardrail-pytest
- Criteria:
  1. Given no `APP_ENVIRONMENT`, When settings load, Then production rules apply and `/docs` is off (AC-19) (type: security; level: unit).
  2. Given any API response including errors, When read, Then the three headers are present (W-5) (type: security; level: api).
  3. Given every nginx location, When requested, Then the same security headers are present (type: security; level: unit).
