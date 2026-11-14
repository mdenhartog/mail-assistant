---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
threat_model: docs/security/web-settings-threat-model.md
status: approved
approver: Marco
date: 2026-11-10
revision: 3 (after the round table of 2026-11-10 and the sign-in and exposure decisions of 2026-11-10)
---

# Web settings: design (phase 3)

Screens and states: `web-settings-screens.md`. Visual direction: ADR-0035 (Pebble, which supersedes the Paper Trail choice of ADR-0031). Sign-in by username and e-mailed code: ADR-0036 (replaces ADR-0024). Local-only exposure: ADR-0037 (replaces ADR-0032). Web notices and the lock: ADR-0033. One api replica: ADR-0034. The settings contract and the audit are those of `adjustable-quiet-hours` (ADR-0025, ADR-0030).

Revision 2 followed the round table (security, UX, QA, product owner) and the decisions of Marco: two releases, the stronger web notice, one api replica, and the hosting target chosen before staging. Revision 3 replaces the OIDC sign-in by the e-mailed code and the internet exposure by local-only access; everything else is unchanged.

## Releases

| | R1 (first usable release) | R2 (later) |
| --- | --- | --- |
| Sign-in | Username and e-mailed code, start-up configuration check (AC-2 to AC-7, AC-24, AC-29 to AC-31) | |
| Page | View and save the four values, last-change line, zone combobox, conflict (AC-1, AC-9 to AC-11, C-7); an expired session sends Marco to sign in and back to `/settings` with the stored values (first half of AC-12) | Reset to defaults (AC-25); typed values kept across session expiry (second half of AC-12) |
| Safety | CSRF and Origin, CSP, headers, route allow-list, 404 for internals, HTTPS and HSTS, limits (AC-8, AC-14 to AC-16, AC-18, AC-19); the web role (AC-17); the Telegram notice with Undo and lock (AC-13, ADR-0033); one security log entry per refusal (first half of AC-20); the retention purge (AC-21, D-19) | The Telegram alert after 5 wrong or expired codes (second half of AC-20) |
| Delivery | Accessibility and responsive states (AC-22, AC-23), contract fixture (AC-26), prod-like edge with the mail catcher, chart, local ingress, NetworkPolicy, secrets | |

AC-12 (second half) and AC-25 stay in R2 by decision of Marco; they are not built. On 2026-11-13 the wrong-code alert (AC-20, second half; U-48, ADR-0039), the automatic lock after 15 wrong codes in 24 hours (U-55, `/web_lock`, `/web_unlock`) and the retention purge (AC-21, D-19; U-49) came into R1; the purge is a gate before production. The table below is the original split; read the three items above as R1.

## Facts in the existing code that shape the design

- The audit record is part of the write: `settings.settings_audit` is an AFTER trigger (SECURITY DEFINER) in the same transaction. The web role needs no grant on `settings_change`, and a failing trigger rolls the write back (second half of AC-17).
- The guard of migration 0006 checks `version = old + 1` and derives the channel from `session_user`; the web role is one more `CASE` line. `settings_change` has no id; records are ordered by `(new->>'version')::int` (as an integer, never as text).
- `schedule_policy.Problem` carries a rule, a value and an example but not the field.
- Things that contradict the spec today: the route inventory test rejects `/auth/*`; the nginx single-page fallback answers 200 for `/docs`, `/healthz`, `/openapi.json` and `/metrics`; `ingress.hsts` exists in the chart values but no template uses it; the ingress routes only `/api`; the `allow-ingress` NetworkPolicy admits every namespace; the prod-like compose profile has no TLS and no migrate job.

## Components and trust boundaries

| Zone | Component | Owns |
| --- | --- | --- |
| Local network | Browser (single-page app from `apps/web`) | Draft values in memory (R1); the CSRF token in memory only |
| B1 | Ingress (private address, ADR-0037) | TLS (1.2 minimum, certificate from a private CA), HTTP to HTTPS redirect, coarse limit, 8 KB body cap |
| App | `web` (nginx, static only) | Assets, CSP for HTML, exact routes `/`, `/login`, `/settings`, everything else 404 |
| App | `api` (FastAPI, one replica, ADR-0034) | Code requests and checks, mail sender, sessions, CSRF, limits, the settings contract |
| B2 | PostgreSQL role `web_settings_runtime` | Schema `web_auth` and a limited write on `settings.schedule` |
| B3 | SMTP relay (the local mail catcher in dev and prod-like) | Delivers the code; reached only over SMTP with STARTTLS from `api` |
| App | `mail-triage` agent | Telegram, web notices, Undo and lock (ADR-0033) |
| Owner | Migrate Job | DDL, grants, the retention purge (last step) |

**Sign-in (two steps, ADR-0036).** `POST /auth/request-code` with the username checks the limits first (client bucket, then the per-username cooldown and hourly cap), then answers the same body, status and timing class whether or not the username is known ("If this username is known, a code has been sent"). For the one configured username it removes the open login request of that username (a new code replaces the old one), generates a six-digit code from the injected code source (a cryptographically secure generator in production), stores a `web_auth.login_request` row (request id, HMAC-SHA-256 hash of the code, expiry 10 minutes, attempts, creation time; capped number of open rows, expired rows removed on insert), sets the request id in `__Host-login` (`HttpOnly`, `Secure`, `SameSite=Lax`, 10 minutes) and hands the message to the mail sender. The answer carries the masked address (`m***@example.com`) and the time the code expires. For an unknown username a dummy hash and the same send path timing are used and nothing is sent.

`POST /auth/verify-code` with the code reads the request id from `__Host-login`, loads the row, and in one transaction checks that it exists, is not expired and has fewer than 5 wrong attempts; it compares the hash in constant time; a wrong code increments the attempts, and the fifth kills the request. A right code deletes the row (`DELETE … RETURNING`, single use), checks the web lock, inserts a session row, sets `__Host-session`, clears `__Host-login` and answers 204; the page then goes to the validated return path. Every failure (no cookie, unknown request, expired, used, exhausted, wrong, another browser's cookie, unknown username, and a locked web, ADR-0033) answers the same generic 400, with the same status, body and headers, so the page never explains the lock and clears `__Host-login` when the request is dead. Every outcome writes a security event (one per client and window for repeats).

**Save.** `PUT /api/settings` with `X-CSRF-Token` goes through request id, body limit, rate limit, session and lock check, Origin and CSRF check, format check, `schedule_policy.validate`, then one `UPDATE … WHERE version = :v RETURNING` (409 when no row). The guard sets the channel to `web` and the audit trigger records the change in the same transaction. At its next run the agent sends the notice (ADR-0033).

## API contract (OpenAPI 3.1, generated and checked in)

Exact path allow-list (AC-15): `/auth/request-code`, `/auth/verify-code`, `/auth/logout`, `/api/session`, `/api/settings`, `/api/places` in R1; `/api/settings/reset` in R2.

| Method and path | Auth | Result |
| --- | --- | --- |
| POST `/auth/request-code` | public, limited, Origin | body `{username}`; 200 `{maskedAddress, expiresAt, resendAfterSeconds}` with `Set-Cookie: __Host-login`, identical for a known and an unknown username (AC-30); 429 with `Retry-After` for the 60 second cooldown and the hourly cap (AC-31); a failed send gives the same 200 as a successful one, is logged and recorded as a `mail_failed` security event, and starts the cooldown and counts towards the hourly cap like any request (AC-29, D-16, ADR-0036) |
| POST `/auth/verify-code` | public, limited, Origin, `__Host-login` | body `{code, returnTo?}`; 204 with the session cookie and the validated return path (anything outside the allow-list becomes `/settings`, AC-6); one generic 400 for every code failure (AC-3, AC-5) whose body carries `attemptsLeft` only when `__Host-login` names a live login request; 429 from the request limits |
| POST `/auth/logout` | session, CSRF, Origin | 204, session deleted, cookie cleared |
| GET `/api/session` | session, `Sec-Fetch-Site` same-origin | `{maskedAddress, csrfToken, idleExpiresAt, absoluteExpiresAt, noticeIntervalMinutes}` (masked address only, never the username or the full address; `noticeIntervalMinutes` is the agent's run interval for the page text) |
| GET `/api/settings` | session | `Settings` (defaults with `version: 0` when no row exists) |
| PUT `/api/settings` | session, CSRF, Origin | body `{values, version}`; 200 `Settings`, 409, 422 |
| GET `/api/places?q=` | session, limited | up to 5 `{zone, label, utcOffsetMinutes}` and a suggestion; same lookup and aliases as Telegram (ADR-0028); the live local time is computed in the browser |
| POST `/api/settings/reset` (R2) | session, CSRF, Origin | body `{version}`; writes `DEFAULT_POLICY` through the same write path |

`Settings` is `{values: {timeZone, quietStart, quietEnd, overviewAt, remindAt}, version, updatedAt, updatedVia}` with `HH:MM` strings and `additionalProperties: false`; the actor is never returned.

Errors are `application/problem+json` with a generic title: 400 (one body for any code failure), 401, 403 (one body for CSRF, Origin and a write without session), 409 with the current `Settings`, 422 with `problems: [{field, rule, value, example}]`, 413, 415, 429 with `Retry-After`. Responses carry `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; HTML carries the CSP (`script-src 'self'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`). HSTS (`max-age=31536000`, no `includeSubDomains`, no preload) comes from nginx and the ingress; the api does not repeat it.

Cookies: `__Host-session` (256-bit random value, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, 12 hours) and `__Host-login` (the login request id, same flags, 10 minutes). No CSRF cookie.

## Backend internals

- **Sign-in code and mail sender.** The code logic is plain Python in the api: a code source (`secrets` in production, injected in tests), HMAC-SHA-256 with the code-hash key, `hmac.compare_digest`. The mail sender is a port (`send_code(address, code, expires_at)`) with an SMTP adapter and a fake used in tests. The SMTP adapter connects to the configured host and port, upgrades with STARTTLS, verifies the certificate against the system trust store, logs in with the send-only account and sends a plain-text message with the code and its validity, no link and no code in the subject. Failures are caught, logged without the address or the code, recorded as a `mail_failed` security event, and answered exactly like a success (ADR-0036). The `httpx`/`httpcore` loggers and the SMTP library logger are pinned to WARNING. Start-up check (AC-4): non-empty username, a valid e-mail address, SMTP host, port and credential present, STARTTLS required (a plain or implicit-TLS-off setting is refused), and the code-hash key and the CSRF key are each at least 32 random bytes and differ.
- **Clock, ids and codes.** `create_app` takes an injected `Clock.now()`, an `IdSource` (session id, login request id, request id) and a `CodeSource`. All expiry is decided in Python from `clock.now()` and passed to SQL as a parameter (no `now()` in queries). The rate window key is `floor(clock.now() / 60)`; the cooldown and the hourly cap are computed from the same clock. The api never accepts a client `X-Request-Id`.
- **Session tables** (schema `web_auth`): `login_request` (request id, code hash, expiry, attempts, created at, sent at, username key), `session` (hashed id, hashed username, `last_seen_at`, `absolute_expires_at`), `security_event` (kind, result, hashed username when unknown, request id) and `web_lock`. The username hash is an HMAC with a secret key; the same value goes into `updated_by` as `web:<32 hex>`. Only the hash of a code is ever stored.
- **CSRF.** The token is derived: `HMAC(csrf_key, session_id)`; it changes when the session id changes, is compared in constant time and is served by `GET /api/session` only for a same-origin request. Every write also needs `Origin` equal to the public origin (missing `Origin` or `Sec-Fetch-Site: cross-site` is refused). No CORS. GET on a write route answers 405 (AC-8).
- **Limits (ADR-0034).** In-process fixed window per client and bucket, checked before any `login_request` insert; the client address is the one the last trusted proxy appended; body limit 8 KB in the api and at the ingress. Per username: a new code only after 60 seconds, at most 5 codes in an hour (every request counts, counted from the `created_at` time of `login_request` rows kept for an hour, also one whose send failed and for decoy rows; D-16), 5 wrong attempts per code. `sent_at` stays empty when a send failed and is not used for the cap. The api has one replica.
- **Settings write.** About 40 lines of SQLAlchemy Core: format check, `validate`, the versioned `UPDATE` (or `INSERT … ON CONFLICT DO NOTHING` at version 0). The database (guard, constraints, audit trigger) is the enforcement; the contract fixture (AC-26) runs in both components.
- **Rule to field.** A static map from rule to field (`quiet_window_*` to start and end, `overview_in_quiet_hours`, `remind_in_quiet_hours`, `zone_unknown`). The package exports its list of rules (`RULES`) so a contract test can check the map covers all of them. Malformed times are rejected at the edge.
- **Database role and migration 0008** (agent chain): schema `web_auth` and its tables (`login_request`, `session`, `security_event`, `web_lock`); the web line in the guard with a check that `updated_by` matches `^web:[0-9a-f]{32}$`; the cursors in `poll_state` for web notices; the notice token record; `settings.contract_version()` which the backend's readiness probe checks instead of the agent's Alembic head. Grants for `web_settings_runtime`: `INSERT` and `UPDATE` on `settings.schedule` limited to `(id,) zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by`, `SELECT` on it, execute on `contract_version()`, the needed rights on the `web_auth` tables, nothing on `public`, nothing on `settings_change`; every new function is `REVOKE`d from `PUBLIC`. The migrate job becomes a list of roles with the SCRAM, no-membership and no-replication rules of ADR-0030; its Secret gains the web role password. The web role's database URL uses `sslmode=verify-full`.
- **Shared package in the image.** The backend image gets `schedule-policy` as a path dependency and `PYTHONTZPATH` as in the agent image (ADR-0028); the build context becomes the repository root. Dependencies added: `sqlalchemy[asyncio]`, `asyncpg` and an async SMTP client (for example `aiosmtplib`, chosen when the unit is built); no OIDC library.
- **Retention (R1, D-19).** `python -m app purge` is the last step of the migrate job (owner role, after migrate and grants; U-49). It deletes `settings.settings_change` rows older than one year and `web_auth.security_event` rows older than 90 days (strictly older than the cutoff), and expired `login_request` and `session` rows (the web role also removes those itself on insert and at start-up). The runtime roles still cannot delete from `settings_change`; the owner purge is its one delete path. There is no CronJob with owner credentials.

## Agent side

- **Web notices (R1, ADR-0033).** Each run selects `settings_change` records with `db_role` other than the agent role and a version above the cursor, sends one notice per change (old and new values, change number, channel, time) with "Undo" and "Undo and lock web sign-in", and advances the cursor. Delivery is at least once. Undo restores the values from before the first announced web change, guarded by the version, with its own token record. The lock writes `web_auth.web_lock`; it is lifted by a Telegram command.
- **Wrong-code alert and automatic lock (R1, ADR-0039).** Counts the `count` of `code_refused` events only: wrong, expired or exhausting codes against a login request of the configured username, not protocol failures and not guesses against decoys; 5 within 10 minutes send one notice (count, time, no code, no username), at most one per 10 minutes; 15 within 24 hours set the web lock and send one notice naming `/web_unlock`. Events seen at or before a lock or an unlock are spent and never count again (kept in memory, so an agent restart forgets it). Other failures (no cookie, malformed body, a dead, unknown or replaced request, a guess against a decoy) are recorded as `code_invalid`, which no alert or lock counts (U-63, U-68).

## Deployment

- Ingress: local only (ADR-0037). No public ingress, no public DNS and no port forward; the ingress or service listens on a private address with a local host name. `/api` and `/auth` to `api`, `/` to `web`, HTTP to HTTPS redirect, TLS 1.2 minimum, a certificate from a private certificate authority that Marco's devices trust (issued by hand or by a cert-manager CA issuer, decided before staging), a certificate expiry alert at least 14 days ahead. Ingress log format uses `$uri`, never the request line with its query string.
- nginx: exact routes for the pages, 404 for the rest; proxy for `/auth/` in compose only.
- NetworkPolicy: `api` and `web` accept ingress from one peer that selects the ingress-controller namespace and its pods; `api` egress to the database, DNS and the SMTP host and port from configuration only (no general TCP 443 rule, no identity-provider egress); no `web-to-api` rule in Kubernetes.
- Secrets (ADR-0029): a SealedSecret `<release>-api` (database URL of the web role, code-hash key, CSRF key, username-hash key); a second SealedSecret for the send-only SMTP credential; the migration Secret gains the web role password. The username, the e-mail address, the SMTP host and port and the public origin are plain values per environment (the address is personal data, not a secret).
- Chart: `replicas: 1` for the api (ADR-0034).
- The local host name, the private certificate authority and the SMTP account are decided before staging; the build and all tests run against the prod-like stack and do not wait for them. Two-step verification on Marco's mailbox is a condition for production (R-1, ADR-0033, ADR-0036).

## Test strategy

| Level | Covers |
| --- | --- |
| Unit and API (in-process app, fake mail sender, fake clock, ids and codes) | AC-3 to AC-8, AC-10, AC-14 to AC-16, AC-29 to AC-31, the generic 400 page |
| Database (testcontainers, as owner, web and agent role) | AC-9, AC-11 races, AC-17 including a failing audit insert, AC-26 |
| Agent (fakes and a real database) | AC-13, the lock and the cursors |
| Component (Vitest, Testing Library, axe) | AC-1, AC-10, AC-23, the combobox and the dialog |
| Playwright `ui-states` (stubbed API, 320, 375, 768 and 1280 px, 200 % text) | AC-22 and AC-23 states |
| Playwright `journey` (prod-like stack, one worker, row reset by owner SQL) | sign-in with the code read from the mail catcher, save, 409 with two contexts, session expiry, CSP, the 404 matrix, redirect and HSTS |
| Chart tests (helm template, kubeconform, kube-linter) | local ingress and no public host, NetworkPolicy with the SMTP egress rule, `replicas: 1`, TLS and HSTS without `includeSubDomains`, no value that disables TLS verification |

Prod-like sequence in CI, in one job (replacing the separate `e2e` and `runtime-role` runs): start the database and the mail catcher, run the migrate service, start the rest with `up --wait`, run the database and role checks, then Playwright. The Caddy edge stays as the TLS edge (HTTPS stays, ADR-0037) under a fixed host name with an alias for the api and web containers; the api and the browser trust its internal CA through `SSL_CERT_FILE` (compose only; no CA or verify setting in the Helm values). The api sends the code over SMTP with STARTTLS to the mail catcher, and the test reads the code from the catcher on port 8025 (its HTTP interface); Playwright signs in once in a `setup` project and reuses the storage state. Sign-in limits (cooldown, hourly cap, request limit) are lowered for e2e through configuration, and the limit tests use a fake clock in the in-process suite. The prod-like check for logs signs in and greps the logs of `api`, `web` and the edge for the code, the username and `code=`. There is no mock identity provider.

## Clickable prototype (ADR-0009)

Decision of Marco: yes. Scope reduced after the round table: the settings form with the zone combobox and live local time, the preview of a zone change, and the conflict banner; the login page and the other states are covered by the screens document (the login page of the prototype is superseded, see the hand-off). It is built as an artifact in the Pebble direction, runs in parallel with the backend units and does not gate them. The tokens unit runs in parallel too.

## Corrections to the spec and the threat model

1. AC-10 and the rule-to-field map above; the package exports `RULES`.
2. C-9: query strings are kept out of every log (api access log off, request logging without queries, ingress and edge formats without them); a grep test runs in the prod-like job.
3. C-2 and AC-15: pre-login values live server-side behind a random login request id; `/api/session` returns the masked address, the CSRF token and the expiry times.
4. AC-17: the web role has no privilege on `settings_change`; W-10: the database enforces channel, version and the shape of `updated_by`; the actor is display only.
5. C-8 and AC-13: Undo goes back to before the burst, with the lock button (ADR-0033); C-9 and AC-20: the alert counts wrong and expired codes only and moves to R2.
6. AC-16: one api replica, in-process limits (ADR-0034).
7. W1 is the e-mailed code (ADR-0036) and W4 is local-only access (ADR-0037); the R-1 review date and the mailbox condition are in the threat model. AC-3 to AC-6, AC-24 and C-1, C-2 and C-9 are rewritten in the spec, AC-29 to AC-31 are new.

## Open before staging

The local host name, the private certificate authority and the SMTP account (send-only); the pinned ingress log format; the exact agent run interval to put in the page text (it is read from the agent configuration).

## Data classification (added in phase 8)

The classification of the stored data is in the threat model (`docs/security/web-settings-threat-model.md`, section Data classification). The design adds these columns and tables to what was planned in revision 3:

| Data | Where | Note |
| --- | --- | --- |
| `client_key` of a security event, `client_hash` of a login request | `web_auth.security_event`, `web_auth.login_request` | Keyed digest (HMAC-SHA-256 under a subkey of the username hash key) of the client address or IPv6 /64, 64 hex characters; never an address. |
| `window`, `count` | `web_auth.security_event` | Minute number and the number of wrong codes of that client in that minute (only `code_refused` raises it). |
| Kind `code_invalid` | `web_auth.security_event` | A refusal that no alert or lock counts (AC-33). |
| `username_hash` of an event | `web_auth.security_event` | Set only where the code stores one (`code_request_refused`, `mail_failed`, `csrf_refused`, `session_start`, `session_end`): a keyed digest of the typed or configured username, 64 hex characters, never the username. |
| `username_key` | `web_auth.login_request` | The same keyed digest of the typed username (real or decoy). |
| `web_notice_token` | agent database | Pre-change values (what Undo restores), the burst id and the token that is the bearer of the Undo button, in clear text; purged when expired (U-71). |
| `username_hash_key` | SealedSecret of the api | Its own key, distinct from the code-hash key and the CSRF key (start-up refuses equal keys). |
| Retention | purge in the migrate job | Security events 90 days, settings audit 1 year, dead login requests 1 hour, expired notice tokens when expired. |
