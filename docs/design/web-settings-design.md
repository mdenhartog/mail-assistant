---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
threat_model: docs/security/web-settings-threat-model.md
status: approved
approver: Marco
date: 2026-11-10
revision: 2 (after the round table of 2026-11-10)
---

# Web settings: design (phase 3)

Screens and states: `web-settings-screens.md`. Visual direction: ADR-0035 (Pebble, which supersedes the Paper Trail choice of ADR-0031). Exposure: ADR-0032. Web notices and the lock: ADR-0033. One api replica: ADR-0034. The settings contract and the audit are those of `adjustable-quiet-hours` (ADR-0025, ADR-0030).

Revision 2 follows the round table (security, UX, QA, product owner) and the decisions of Marco: two releases, the stronger web notice, one api replica, and the hosting target chosen before staging.

## Releases

| | R1 (first usable release) | R2 (later) |
| --- | --- | --- |
| Sign-in | Login with OIDC, exact (issuer, `sub`), start-up configuration check (AC-2 to AC-7, AC-24) | |
| Page | View and save the four values, last-change line, zone combobox, conflict (AC-1, AC-9 to AC-11, C-7); an expired session sends Marco to sign in and back to `/settings` with the stored values (first half of AC-12) | Reset to defaults (AC-25); typed values kept across session expiry (second half of AC-12) |
| Safety | CSRF and Origin, CSP, headers, route allow-list, 404 for internals, HTTPS and HSTS, limits (AC-8, AC-14 to AC-16, AC-18, AC-19); the web role (AC-17); the Telegram notice with Undo and lock (AC-13, ADR-0033); one security log entry per refusal (first half of AC-20) | The Telegram alert after 5 refused sign-ins (second half of AC-20); audit retention (AC-21) |
| Delivery | Accessibility and responsive states (AC-22, AC-23), contract fixture (AC-26), prod-like edge with a mock provider, chart, ingress, NetworkPolicy, secrets | |

AC-12 (second half), AC-20 (second half), AC-21 and AC-25 move to R2 by decision of Marco. The retention purge has nothing to delete before November 2027.

## Facts in the existing code that shape the design

- The audit record is part of the write: `settings.settings_audit` is an AFTER trigger (SECURITY DEFINER) in the same transaction. The web role needs no grant on `settings_change`, and a failing trigger rolls the write back (second half of AC-17).
- The guard of migration 0006 checks `version = old + 1` and derives the channel from `session_user`; the web role is one more `CASE` line. `settings_change` has no id; records are ordered by `(new->>'version')::int` (as an integer, never as text).
- `schedule_policy.Problem` carries a rule, a value and an example but not the field.
- Things that contradict the spec today: the route inventory test rejects `/auth/*`; the nginx single-page fallback answers 200 for `/docs`, `/healthz`, `/openapi.json` and `/metrics`; `ingress.hsts` exists in the chart values but no template uses it; the ingress routes only `/api`; the `allow-ingress` NetworkPolicy admits every namespace; the prod-like compose profile has no TLS, no identity provider and no migrate job.

## Components and trust boundaries

| Zone | Component | Owns |
| --- | --- | --- |
| Internet | Browser (single-page app from `apps/web`) | Draft values in memory (R1); the CSRF token in memory only |
| B1 | Ingress | TLS (1.2 minimum), HTTP to HTTPS redirect, coarse limit, 8 KB body cap |
| App | `web` (nginx, static only) | Assets, CSP for HTML, exact routes `/`, `/login`, `/settings`, everything else 404 |
| App | `api` (FastAPI, one replica, ADR-0034) | OIDC client, sessions, CSRF, limits, the settings contract |
| B2 | PostgreSQL role `web_settings_runtime` | Schema `web_auth` and a limited write on `settings.schedule` |
| B3 | OIDC provider | Identity; reached only over TLS from `api` |
| App | `mail-triage` agent | Telegram, web notices, Undo and lock (ADR-0033) |
| Owner | Migrate Job | DDL, grants (the retention purge joins it in R2) |

**Sign-in.** `GET /auth/login` checks the limit first, then stores state, nonce, PKCE verifier and the return path in a `web_auth.login_flow` row (capped number of open rows; expired rows are removed on insert), sets a random id in `__Host-login` (10 minutes) and redirects to the provider (S256, `openid email profile`, exact redirect URI). The callback deletes the row by cookie id with `DELETE … RETURNING` (single use), compares `state`, exchanges the code, validates the ID token (signature through the issuer's JWKS, `iss`, `aud`, `azp`, `exp`, `nonce`) against the injected clock, compares the exact pair (issuer, `sub`), checks the web lock, inserts a session row, sets `__Host-session`, clears `__Host-login` and redirects with 303. The 400 and 403 pages also clear `__Host-login`. Every outcome writes a security event (one per client and window for repeats).

**Save.** `PUT /api/settings` with `X-CSRF-Token` goes through request id, body limit, rate limit, session and lock check, Origin and CSRF check, format check, `schedule_policy.validate`, then one `UPDATE … WHERE version = :v RETURNING` (409 when no row). The guard sets the channel to `web` and the audit trigger records the change in the same transaction. At its next run the agent sends the notice (ADR-0033).

## API contract (OpenAPI 3.1, generated and checked in)

Exact path allow-list (AC-15): `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/session`, `/api/settings`, `/api/places` in R1; `/api/settings/reset` in R2.

| Method and path | Auth | Result |
| --- | --- | --- |
| GET `/auth/login?return_to=` | public, limited | 302 to the provider; any `return_to` other than `/settings` becomes `/settings` (AC-6) |
| GET `/auth/callback?code&state` | public, limited | 303 with the session cookie; 403 static page "This account is not allowed for this app"; 400 static page "Sign-in failed, try again" |
| POST `/auth/logout` | session, CSRF, Origin | 204, session deleted, cookie cleared |
| GET `/api/session` | session, `Sec-Fetch-Site` same-origin | `{email, csrfToken, idleExpiresAt, absoluteExpiresAt}` |
| GET `/api/settings` | session | `Settings` (defaults with `version: 0` when no row exists) |
| PUT `/api/settings` | session, CSRF, Origin | body `{values, version}`; 200 `Settings`, 409, 422 |
| GET `/api/places?q=` | session, limited | up to 5 `{zone, label, utcOffsetMinutes}` and a suggestion; same lookup and aliases as Telegram (ADR-0028); the live local time is computed in the browser |
| POST `/api/settings/reset` (R2) | session, CSRF, Origin | body `{version}`; writes `DEFAULT_POLICY` through the same write path |

`Settings` is `{values: {timeZone, quietStart, quietEnd, overviewAt, remindAt}, version, updatedAt, updatedVia}` with `HH:MM` strings and `additionalProperties: false`; the actor is never returned.

Errors are `application/problem+json` with a generic title: 401, 403 (one body for CSRF, Origin and a write without session), 409 with the current `Settings`, 422 with `problems: [{field, rule, value, example}]`, 413, 415, 429 with `Retry-After`. Responses carry `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; HTML carries the CSP (`script-src 'self'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`), also the static callback pages the api serves. HSTS (`max-age=31536000; includeSubDomains`, no preload) comes from nginx and the ingress; the api does not repeat it.

Cookies: `__Host-session` (256-bit random value, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, 12 hours) and `__Host-login` (same flags, 10 minutes). No CSRF cookie.

## Backend internals

- **Sign-in library.** Authlib (`AsyncOAuth2Client`) with joserfc; algorithms pinned to RS256 and ES256; discovery only against the configured `https` issuer whose metadata `issuer` matches exactly; JWKS cached and refreshed at most once per interval on an unknown `kid`; RP logout only when the provider advertises it. The `httpx`, `httpcore` and `authlib` loggers are pinned to WARNING and the provider's `error_description` is never stored raw. Start-up check (AC-4): HTTPS issuer, non-empty allowed `sub`, non-empty client secret, HTTPS public origin, redirect URI = origin + `/auth/callback`, and the subject-hash key and CSRF key are each at least 32 random bytes and differ.
- **Clock and ids.** `create_app` takes an injected `Clock.now()` and an `IdSource` (session id, state, nonce, request id). All expiry is decided in Python from `clock.now()` and passed to SQL as a parameter (no `now()` in queries); ID-token validation gets `now` explicitly; the mock provider issues tokens from the same clock. The rate window key is `floor(clock.now() / 60)`. The api never accepts a client `X-Request-Id`.
- **Session tables** (schema `web_auth`): `login_flow`, `session` (hashed id, hashed subject, e-mail for display, `last_seen_at`, `absolute_expires_at`), `security_event` (kind, issuer, hashed subject, request id) and `web_lock`. The subject hash is an HMAC with a secret key; the same value goes into `updated_by` as `web:<32 hex>`.
- **CSRF.** The token is derived: `HMAC(csrf_key, session_id)`; it changes when the session id changes, is compared in constant time and is served by `GET /api/session` only for a same-origin request. Every write also needs `Origin` equal to the public origin (missing `Origin` or `Sec-Fetch-Site: cross-site` is refused). No CORS. GET on a write route answers 405 (AC-8).
- **Limits (ADR-0034).** In-process fixed window per client and bucket, checked before any `login_flow` insert; the client address is the one the last trusted proxy appended; body limit 8 KB in the api and at the ingress. The api has one replica.
- **Settings write.** About 40 lines of SQLAlchemy Core: format check, `validate`, the versioned `UPDATE` (or `INSERT … ON CONFLICT DO NOTHING` at version 0). The database (guard, constraints, audit trigger) is the enforcement; the contract fixture (AC-26) runs in both components.
- **Rule to field.** A static map from rule to field (`quiet_window_*` to start and end, `overview_in_quiet_hours`, `remind_in_quiet_hours`, `zone_unknown`). The package exports its list of rules (`RULES`) so a contract test can check the map covers all of them. Malformed times are rejected at the edge.
- **Database role and migration 0008** (agent chain): schema `web_auth` and its tables; the web line in the guard with a check that `updated_by` matches `^web:[0-9a-f]{32}$`; the cursors in `poll_state` for web notices; the notice token record; `settings.contract_version()` which the backend's readiness probe checks instead of the agent's Alembic head. Grants for `web_settings_runtime`: `INSERT` and `UPDATE` on `settings.schedule` limited to `(id,) zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by`, `SELECT` on it, execute on `contract_version()`, the needed rights on the `web_auth` tables, nothing on `public`, nothing on `settings_change`; every new function is `REVOKE`d from `PUBLIC`. The migrate job becomes a list of roles with the SCRAM, no-membership and no-replication rules of ADR-0030; its Secret gains the web role password. The web role's database URL uses `sslmode=verify-full`.
- **Shared package in the image.** The backend image gets `schedule-policy` as a path dependency and `PYTHONTZPATH` as in the agent image (ADR-0028); the build context becomes the repository root. Dependencies added: `sqlalchemy[asyncio]`, `asyncpg`, `authlib`, `joserfc`, `httpx`.
- **Retention (R2).** `python -m app purge` becomes a step of the migrate job (owner role). Expired `login_flow` and `session` rows are removed by the web role itself on insert and at start-up. There is no CronJob with owner credentials.

## Agent side

- **Web notices (R1, ADR-0033).** Each run selects `settings_change` records with `db_role` other than the agent role and a version above the cursor, sends one notice per change (old and new values, change number, channel, time) with "Undo" and "Undo and lock web sign-in", and advances the cursor. Delivery is at least once. Undo restores the values from before the first announced web change, guarded by the version, with its own token record. The lock writes `web_auth.web_lock`; it is lifted by a Telegram command.
- **Refused-sign-in alert (R2).** Counts only `signin_refused` events (a valid token with the wrong account), not protocol failures such as a missing state; 5 within 10 minutes send one notice (count, issuer, time, no `sub`), at most one per 10 minutes. Protocol failures are logged and counted separately.

## Deployment

- Ingress: `/api` and `/auth` to `api`, `/` to `web`, HTTP to HTTPS redirect, TLS 1.2 minimum, certificates through cert-manager (issuer decided before staging), a certificate expiry alert at least 14 days ahead. Ingress log format uses `$uri`, never the request line with its query string.
- nginx: exact routes for the pages, 404 for the rest; proxy for `/auth/` in compose only.
- NetworkPolicy: `api` and `web` accept ingress from one peer that selects the ingress-controller namespace and its pods; `api` egress to the database, DNS and TCP 443 outside private ranges (recorded as an accepted risk, reviewed 2027-05-10); no `web-to-api` rule in Kubernetes.
- Secrets (ADR-0029): a SealedSecret `<release>-api` (client secret, database URL of the web role, subject-hash key, CSRF key); the migration Secret gains the web role password. Issuer, client id, allowed `sub` and public origin are plain values per environment.
- Chart: `replicas: 1` for the api (ADR-0034).
- The domain, certificate issuer, cluster and ingress controller are decided before staging; the build and all tests run against the prod-like stack and do not wait for them. Provider account protection (two-step verification or a passkey) is a condition for production (ADR-0033).

## Test strategy

| Level | Covers |
| --- | --- |
| Unit and API (in-process app, fake provider, fake clock and ids) | AC-3 to AC-8, AC-10, AC-14 to AC-16, the 400 and 403 pages |
| Database (testcontainers, as owner, web and agent role) | AC-9, AC-11 races, AC-17 including a failing audit insert, AC-26 |
| Agent (fakes and a real database) | AC-13, the lock and the cursors |
| Component (Vitest, Testing Library, axe) | AC-1, AC-10, AC-23, the combobox and the dialog |
| Playwright `ui-states` (stubbed API, 320, 375, 768 and 1280 px, 200 % text) | AC-22 and AC-23 states |
| Playwright `journey` (prod-like stack, one worker, row reset by owner SQL) | sign-in, save, 409 with two contexts, session expiry, CSP, the 404 matrix, redirect and HSTS |
| Chart tests (helm template, kubeconform, kube-linter) | ingress paths, NetworkPolicy, `replicas: 1`, TLS and HSTS, no value that disables TLS verification |

Prod-like sequence in CI, in one job (replacing the separate `e2e` and `runtime-role` runs): start the database, run the migrate service, start the rest with `up --wait`, run the database and role checks, then Playwright. The mock provider is served over HTTPS through the Caddy edge under a fixed host name with an alias for the api and web containers; the api trusts the internal CA through `SSL_CERT_FILE` (compose only; no CA or verify setting in the Helm values); Playwright signs in once in a `setup` project and reuses the storage state; the mock provider has a non-interactive sign-in (`login_hint`) with the allowed user and a second user that gets the 403 page. Sign-in limits are raised for e2e through configuration. The prod-like check for logs signs in and greps the logs of `api`, `web` and the edge for the code, the state and `code=`.

## Clickable prototype (ADR-0009)

Decision of Marco: yes. Scope reduced after the round table: the settings form with the zone combobox and live local time, the preview of a zone change, and the conflict banner; the login page and the other states are covered by the screens document. It is built as an artifact in the Pebble direction, runs in parallel with the backend units and does not gate them. The tokens unit runs in parallel too.

## Corrections to the spec and the threat model

1. AC-10 and the rule-to-field map above; the package exports `RULES`.
2. C-9: query strings are kept out of every log (api access log off, request logging without queries, ingress and edge formats without them); a grep test runs in the prod-like job.
3. C-2 and AC-15: pre-login values live server-side behind a random id; `/api/session` also returns the e-mail and the CSRF token.
4. AC-17: the web role has no privilege on `settings_change`; W-10: the database enforces channel, version and the shape of `updated_by`; the actor is display only.
5. C-8 and AC-13: Undo goes back to before the burst, with the lock button (ADR-0033); C-9 and AC-20: the alert counts refused sign-ins only and moves to R2.
6. AC-16: one api replica, in-process limits (ADR-0034).
7. W4 is decided (ADR-0032); the R-1 review date and the provider account condition are added (ADR-0033).

## Open before staging

Domain, certificate issuer, cluster and ingress controller; the pinned ingress log format; the exact agent run interval to put in the page text (it is read from the agent configuration).
