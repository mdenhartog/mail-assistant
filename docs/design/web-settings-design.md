---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
threat_model: docs/security/web-settings-threat-model.md
status: draft
date: 2026-11-10
---

# Web settings: design (phase 3)

Screens and states are in `web-settings-screens.md`. Visual direction: ADR-0031 (Paper Trail). Public exposure: ADR-0032. The settings contract and the audit are those of `adjustable-quiet-hours` (ADR-0025, ADR-0030). This document turns the approved spec into components, contracts and units; decisions marked **proposed** need approval at the end of this phase.

## Facts in the existing code that shape the design

- The audit record is part of the write: `settings.settings_audit` is an AFTER trigger (SECURITY DEFINER) in the same transaction, so the web role needs no grant on `settings_change`, and a failing trigger rolls the write back (second half of AC-17).
- The guard trigger of migration 0006 checks `version = old + 1` and derives the channel from `session_user`. The web role is one more `CASE` line.
- `settings_change` has no id; its records are ordered by `new->>'version'`, which rises by exactly one per write.
- `schedule_policy.Problem` carries a rule, a value and an example but not the field.
- Things that contradict the spec today: the route inventory test rejects `/auth/*`; the nginx single-page fallback answers 200 for `/docs`, `/healthz`, `/openapi.json` and `/metrics` (AC-19 needs 404); `ingress.hsts` exists in the chart values but no template uses it; the ingress routes only `/api`; the `allow-ingress` NetworkPolicy admits every namespace; the prod-like compose profile has no TLS, no identity provider and no migrate job.

## Components and trust boundaries

| Zone | Component | Owns |
| --- | --- | --- |
| Internet | Browser (single-page app from `apps/web`) | Draft form values in `sessionStorage` (no secrets); the CSRF token in memory only |
| B1 | Ingress | TLS, HTTP to HTTPS redirect, coarse limit, 8 KB body cap |
| App | `web` (nginx, static only) | Assets, CSP for HTML, exact routes `/`, `/login`, `/settings`, everything else 404 |
| App | `api` (FastAPI, backend for the page) | OIDC client, sessions, CSRF, rate limits, the settings HTTP contract |
| B2 | PostgreSQL role `web_settings_runtime` | Schema `web_auth` (data, not ownership) and a limited write on `settings.schedule` |
| B3 | OIDC provider | Identity; reached only over TLS from `api` |
| App | `mail-triage` agent | Telegram, notices, Undo, refused-sign-in alert (reads, never receives calls) |
| Owner | Migrate Job, purge CronJob | DDL, grants, retention (owner role) |

Sign-in: `GET /auth/login` stores state, nonce, PKCE verifier and the return path in a `web_auth.login_flow` row and sets a random id in a `__Host-login` cookie (10 minutes) and redirects to the provider (S256, `openid email profile`, exact redirect URI). The callback deletes the row by cookie id (single use), compares `state`, exchanges the code, validates the ID token (signature through the issuer's JWKS, `iss`, `aud`, `azp`, `exp`, `nonce`), compares the exact pair (issuer, `sub`), inserts a session row, sets `__Host-session` and redirects with 303 to an allow-listed path. Every outcome writes a security event.

Save: `PUT /api/settings` with `X-CSRF-Token` goes through request id, body limit, rate limit, session check (idle and absolute), Origin and CSRF check, format check, `schedule_policy.validate`, then one `UPDATE … WHERE version = :v RETURNING` (409 when no row). The guard sets the channel to `web` and the audit trigger records the change in the same transaction. At its next run the agent sends the Telegram notice with Undo (C-8).

## API contract (OpenAPI 3.1, generated and checked in)

Exact path allow-list (AC-15): `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/session`, `/api/settings`, `/api/settings/reset`, `/api/places`.

| Method and path | Auth | Result |
| --- | --- | --- |
| GET `/auth/login?return_to=` | public, rate-limited | 302 to the provider; a `return_to` other than `/settings` becomes `/settings` (AC-6) |
| GET `/auth/callback?code&state` | public, rate-limited | 303 to the return path with the session cookie; 403 static page "This account is not allowed for this app"; 400 static page "Sign-in failed, try again" |
| POST `/auth/logout` | session, CSRF, Origin | 204, session deleted, cookie cleared |
| GET `/api/session` | session | `{email, csrfToken, idleExpiresAt, absoluteExpiresAt}` |
| GET `/api/settings` | session | `Settings` (defaults with `version: 0` when no row exists) |
| PUT `/api/settings` | session, CSRF, Origin | body `{values, version}`; 200 `Settings`, 409, 422 |
| POST `/api/settings/reset` | session, CSRF, Origin | body `{version}`; writes `DEFAULT_POLICY` through the same write path (AC-25) |
| GET `/api/places?q=` | session, rate-limited | up to 5 `{zone, label, utcOffsetMinutes}` and a suggestion; the same lookup as Telegram (ADR-0028); the live local time is computed in the browser |

`Settings` is `{values: {timeZone, quietStart, quietEnd, overviewAt, remindAt}, version, updatedAt, updatedVia}` with `HH:MM` strings and `additionalProperties: false`. The actor is never returned.

Errors are `application/problem+json` with a generic title: 401 unauthenticated, 403 forbidden (the same body for CSRF, Origin and a write without a session), 409 conflict with the current `Settings`, 422 invalid with `problems: [{field, rule, value, example}]`, 413, 415, 429 with `Retry-After`. Responses carry `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; HTML carries the CSP (`script-src 'self'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`); HSTS `max-age=31536000; includeSubDomains` comes from nginx and from an api middleware so any ingress controller works.

Cookies: `__Host-session` (256-bit random value, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, 12 hours) and `__Host-login` (same flags, 10 minutes). There is no CSRF cookie.

## Backend internals (proposed decisions)

- **Sign-in implementation.** Authlib (`AsyncOAuth2Client`) with joserfc for ID-token verification; algorithms pinned to RS256 and ES256; discovery only against the configured `https` issuer whose metadata `issuer` must match exactly; JWKS cached and refreshed once on an unknown `kid`; no signed-cookie session; RP-initiated logout only when the provider advertises it (Google does not). Start-up check (AC-4) as a Pydantic validator: HTTPS issuer, non-empty allowed `sub`, non-empty client secret, HTTPS public origin, redirect URI = origin + `/auth/callback`.
- **Session tables** (schema `web_auth`): `login_flow`, `session` (hashed id, hashed CSRF token, hashed subject, e-mail for display, `last_seen_at`, `absolute_expires_at`), `security_event` (kind, issuer, hashed subject, request id), `rate_bucket`. The subject hash is an HMAC with a secret key so a dictionary of numeric `sub` values does not match; the same hash goes into `updated_by` as `web:<32 hex>`.
- **CSRF.** Synchronizer token: hash stored on the session row, delivered by `GET /api/session`, sent as `X-CSRF-Token`, compared in constant time, together with a strict check that `Origin` equals the public origin (a missing `Origin` or `Sec-Fetch-Site: cross-site` is refused). No CORS. A GET on a write route answers 405 (AC-8).
- **Rate and body limits.** Several replicas are possible, so limits live in the backend with a fixed window per client and bucket in `web_auth.rate_bucket` (exact across replicas, configurable, testable). The client address comes from `X-Forwarded-For` only from the ingress CIDR. The ingress keeps a coarse limit and the 8 KB cap as a backstop; the api enforces 8 KB too.
- **Settings write.** About 40 lines of SQLAlchemy Core in `app/services/settings_store.py`, with the format check, `validate`, and the versioned `UPDATE` (or `INSERT … ON CONFLICT DO NOTHING` at version 0). The database (guard, constraints, audit trigger) is the real enforcement and the shared contract fixture (AC-26) runs in both components.
- **Database role and migration.** The agent chain owns migration 0008: schema `web_auth` and its tables, the web channel line in the guard, cursors in `poll_state` (`web_notice_version`, `security_alert_event_id`), and `settings.contract_version()` which the backend's readiness probe checks instead of the agent's Alembic head. A grants file for `web_settings_runtime`: select and insert on `settings.schedule`, update on the value columns only, execute on `contract_version()`, the needed rights on the `web_auth` tables, nothing on `public` and nothing on `settings_change`. The migrate job becomes a list of roles with the same SCRAM, no-membership and no-replication rules, and its Secret gains the web role password.
- **Retention (AC-21).** A daily CronJob under the owner role runs `python -m app purge`: audit and security records older than one year and expired login, session and rate rows.
- **Shared package in the image.** The backend image gets `schedule-policy` as a path dependency and `PYTHONTZPATH` set as in the agent image (ADR-0028); the build context becomes the repository root.
- **Route inventory.** The test becomes an exact path allow-list; auth markers `signed_in` and `signed_in_csrf` for routes.

## Agent side (proposed decisions)

- Web notices (C-8): each run selects `settings_change` records not written by the agent role with a version above the cursor, sends one notice per change with old and new values, the change number, the channel and an Undo button, then advances the cursor. Delivery is at least once and an Undo is guarded by the version, so a duplicate is harmless. An Undo token must not replace a Telegram dialogue in progress (ADR-0026): check how the quiet-hours Undo is stored and give web notices their own short-lived token record if needed.
- Refused-sign-in alert (C-9): each run counts refused or failed sign-ins in the last 10 minutes after the alert cursor; at 5 or more it sends one notice (count, issuer, time, no `sub`) and moves the cursor. At most one alert per 10 minutes. The latency equals the agent's run interval. The backend gets no Telegram client (ADR-0019).

## Deployment

- Ingress: `/api` and `/auth` to `api`, `/` to `web`, HTTP to HTTPS redirect, certificates through cert-manager (issuer decided with the domain). `ingress.hsts` is wired up or removed.
- nginx: exact routes for the pages, 404 for the rest; proxy for `/auth/` in compose only.
- NetworkPolicy: `api` and `web` accept ingress only from the ingress-controller namespace; `api` egress to the database, DNS and TCP 443 outside private ranges (the provider); no `web-to-api` rule in Kubernetes.
- Secrets (ADR-0029): a SealedSecret `<release>-api` with the client secret, the database URL of the web role and the subject-hash key; the migration Secret gains the web role password. Issuer, client id, allowed `sub` and public origin are plain values per environment.
- Prod-like compose: a Caddy edge with an internal CA (`:8443`, `:8080` redirecting with HSTS) and a mock OIDC provider served over HTTPS, so the HTTPS-issuer rule of AC-4 holds without a test flag; the migrate service stays out of the profile (it cannot be part of `up --wait`) and runs as a separate step as in the `runtime-role` job. The negative token cases of AC-5 run in pytest against an in-process fake provider.

## Corrections to the spec and the threat model (to approve)

1. AC-10: the page needs the field for each problem. The backend keeps a static map from rule to field (`quiet_window_*` to start and end, `overview_in_quiet_hours`, `remind_in_quiet_hours`, `zone_unknown`) and a contract test checks that it covers every rule the package exports. Malformed times are rejected at the edge. Alternative: a `field` on `Problem` (touches the mutation-tested package).
2. C-9: the authorization code and `state` would end up in access logs. The api access log is switched off, request logging drops query strings, ingress log formats exclude them, and a test greps the logs for `code=`.
3. C-2 and AC-15: pre-login values live server-side behind a random id in the cookie (truly single use, no encryption key), not in the cookie itself; `/api/session` also returns the e-mail and the CSRF token.
4. AC-17: the backend role has no privilege at all on `settings_change` (it does not need an insert grant); and W-10: the channel is enforced by the database, the actor `updated_by` is chosen by the writer and is display only.
5. W4 is decided (ADR-0032).

## Units (outline, detailed in the plan)

Tokens and the clickable prototype; backend skeleton and configuration checks; sign-in and sessions; CSRF, rate limits and headers; settings API; migration 0008 and role grants; page shell and sign-in screens; settings form and zone combobox; conflict, session expiry and reset; agent notices and alert; purge CronJob; chart, ingress, NetworkPolicy and secrets; prod-like edge and fake provider; end-to-end and accessibility checks.

## Open decisions for Marco

1. Authlib with joserfc, or a hand-written client on httpx and joserfc (recommended: Authlib).
2. The `web_auth` schema and the web role migrated by the agent's chain (recommended) or a separate backend chain with its own owner job.
3. Owner credentials in a daily purge CronJob (recommended) or purge inside the migrate job.
4. HSTS `preload` (hard to undo; recommended: no for now).
5. Domain, certificate issuer, cluster and ingress controller (needed before production, not for the build).
