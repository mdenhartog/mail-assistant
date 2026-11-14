---
intent: INT-002
feature: web-settings
---

# U-web-settings-37: Prod-like TLS edge and nginx exact routes (R1)

- Layer: infra
- Contract: the `prod-like` compose profile gains a Caddy edge (HTTPS from an internal CA, HTTP to HTTPS redirect, HSTS `max-age=31536000` without `includeSubDomains` and without preload, `/api` and `/auth` to `api`, the rest to `web`, a log format without the query string) under a fixed host name with an alias for `api` and `web`. In the same PR `apps/web/nginx.conf` serves exactly `/`, `/login`, `/settings` (the single page), `/assets/*` and answers 404 for everything else, and loses its `/api/` `proxy_pass` (the edge routes); the existing `e2e` job and `home.spec.ts` are moved to the edge (base URL and CA trust) so `main` stays green. The existing page `App.tsx` placeholder is untouched here.
- Files: `compose.yaml`, `deploy/prod-like/Caddyfile`, `deploy/prod-like/certs.sh`, `apps/web/nginx.conf`, `apps/web/Dockerfile`, `apps/web/playwright.config.ts`, `.github/workflows/ci.yml`
- Depends on: U-web-settings-02
- Parallel: yes (with the backend and web units)
- Guardrails: guardrail-compose, guardrail-docker, guardrail-tls-certificates
- Criteria:
  1. Given the profile started with `up -d --wait`, When finished, Then db, api, web and edge are healthy and the existing `e2e` job passes through the edge (type: happy; level: ci).
  2. Given plain HTTP to the edge, When requested, Then a redirect to HTTPS; an HTTPS response carries `Strict-Transport-Security: max-age=31536000` without `includeSubDomains` and without `preload` (AC-18, W-9) (type: security; level: image).
  3. Given `/`, `/login`, `/settings` through the edge, When requested, Then 200 with the index page, the CSP and `nosniff`; `/assets/<hash>.js` is served immutable (type: happy; level: image).
  4. Given `/docs`, `/redoc`, `/openapi.json`, `/healthz`, `/readyz`, `/metrics`, `/api/docs`, `/api/openapi.json`, `/api/readyz`, `/auth/anything-unknown` and `/anything`, When requested through the edge, Then 404 each (AC-19, W-6) (type: security; level: image).
  5. Given the web image, When requested directly for `/auth/login` or `/api/settings`, Then 404 and the config has no `proxy_pass` (type: security; level: image).
  6. Given the edge log, When a request with a query string is made, Then the logged line has the path only (AC-20, W-13) (type: security; level: image).
  7. Given the new services, When read, Then `read_only`, `no-new-privileges` and `cap_drop: ALL` apply and ports bind to `127.0.0.1` only (type: security; level: ci).
  8. Given `docker compose --profile prod-like config`, When searched, Then no literal secret (type: security; level: ci).
