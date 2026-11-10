---
intent: INT-002
feature: web-settings
title: Web settings (login and settings page)
spec: docs/specs/web-settings.md
design: docs/design/web-settings-design.md
screens: docs/design/web-settings-screens.md
threat-model: docs/security/web-settings-threat-model.md
status: draft
date: 2026-11-10
---

The second feature of INT-002. It adds the first internet-facing surface: a login page (generic OIDC) and a settings page in `apps/web`, a session and settings API in `backend`, one more database role and schema (migration 0008 in the agent chain), web notices with Undo and lock in `agents/mail-triage`, and the edge (nginx, ingress, NetworkPolicy, prod-like stack with Caddy and a mock provider). Built in two releases (W5): R1 first, R2 later (marked per unit).

Each unit gets its own git worktree and branch `feat/INT-002/web-settings/<nn>` and is built test-first: a failing test is shown before the implementation. A test is named after its criterion (`test_given_<x>_when_<y>_then_<z>` in Python, the same sentence as `it(...)` in Vitest and Playwright). Commits carry `Refs: INT-002` and `Unit: U-web-settings-<nn>`.

Common guardrails for every unit: `guardrail-python` + `guardrail-pytest` for Python, `guardrail-typescript` + `guardrail-vitest-rtl` for web code. Others are listed per unit.

## Test rules and levels

- Time and ids are injected. `create_app(settings, *, clock, ids)` takes a `Clock` and an `IdSource` (U-04); tests use `FakeClock` and a counting `FakeIds`; no `datetime.now()`, no `now()` in SQL (expiry is decided in Python and passed as a parameter), no sleeps (barriers and the fake clock). The browser side injects its clock the same way.
- No real Google, Telegram or network. The in-process fake OIDC provider (U-10) signs with a configurable key and claims; the same code runs as the mock provider container in the prod-like stack (U-31).
- Real PostgreSQL (testcontainers) for everything that touches `web_auth`, `settings` or a grant. Backend DB tests apply the agent migration chain as owner, then `grants.sql`, then connect as `web_settings_runtime` (fixture from U-08).
- A canary zone `Pacific/Kiritimati` and a canary `sub` must never appear in captured logs; one shared check in `backend/tests/conftest.py` (lesson of `adjustable-quiet-hours`).
- Levels named in the criteria: **unit** (pure function, no I/O), **db** (testcontainers PostgreSQL), **api** (in-process FastAPI app with fake provider, fake clock and ids), **agent** (agent use case with fakes plus a real database), **component** (Vitest, Testing Library, axe with contrast off in jsdom), **playwright** (`ui-states` with a stubbed API, or `journey` against the prod-like stack), **chart** (`helm template`, kubeconform, kube-linter, a Python or Node test over the render), **image** (a built image started by the test), **ci** (workflow file read by a test), **review** (checklist in a hand-off document, checked by a person).
- Coverage at least 90 % on changed code. Mutation score at least 85 % on the pure security modules (U-33, ADR-0030).

## Order and parallelism

```text
Design      U-01 prototype hand-off (artifact)        U-02 tokens: Pebble + contrast test        (parallel with everything below)
Foundation  U-03 image + shared package ─► U-04 backend foundation ─► U-05 HTTP surface
            U-06 migration 0008 ─► U-07 grants + web role in migrate.py ─► U-08 DB access + readiness ─► U-09 security events + log hygiene
Sign-in     U-10 token validator + fake provider (needs U-04)
            U-11 login flow (U-05, U-08, U-09, U-10) ─┐
            U-12 session (U-05, U-08, U-09) ──────────┴─► U-13 callback ─► U-14 CSRF, Origin, logout, /api/session
            U-15 limits (U-05, U-09, U-11)
API         U-16 write repository (U-06, U-07, U-08) ─► U-17 settings routes + RULES (U-05, U-12, U-14, U-15, U-16) ─► U-18 places route
Agent       U-19 web notices (U-06, U-07) ─► U-20 notice buttons + unlock command            (parallel with Foundation, Sign-in and API)
Web         U-22 primitives (needs only U-02; parallel with the backend)
            U-21 shell + API client (U-02, U-17); U-23 login page (U-21, U-22) · U-24 settings form (U-01, U-21, U-22)
            U-25 ZoneCombobox (U-18, U-24) ─► U-26 save feedback + zone preview · U-27 conflict (U-24) ─► U-28 ui-states
Edge        U-29 nginx + ingress (parallel with everything) ─► U-30 chart: NetworkPolicy, replicas, secrets
            U-31 prod-like profile (U-03, U-07, U-10) ─► U-32 journey + one CI job (needs U-13, U-14, U-17, U-24, U-27, U-28, U-30, U-31)
            U-33 mutation scope (U-10, U-11, U-12, U-14, U-15, U-17)
R2          U-34 reset backend ─► U-35 reset web · U-36 draft kept · U-37 refused-sign-in alert · U-38 audit retention purge
```

Build-green rules (lessons of `adjustable-quiet-hours`, section "Changes made during the build"):

- U-03 wires the shared package into the backend (lockfile, image, compose, CI) before any backend code imports it, as U-quiet-hours-01b did for the agent. The `images` CI job builds the backend from the repo root from U-03 on.
- Migration 0008 is the only new migration of R1 (U-06). The R2 retention purge (U-38) adds no migration. If another migration lands first, rename before merge; do not renumber after.
- A one-shot compose service (migrate) is not part of `up --wait` (it exits and counts as failed). The CI job runs it with `docker compose run --rm` before `up --wait` (U-32).
- U-01, U-02, U-03, U-06, U-19 and U-29 have no dependency and run in parallel. U-22 runs in parallel with the backend (it needs only tokens). U-21 needs the checked-in OpenAPI of U-17 for its generated client.
- The tokens unit and the prototype do not gate the backend (design, section "Clickable prototype"). They gate the production screens: U-22 needs U-02, U-24 and later need U-01 approved.

## Units

### U-web-settings-01: Clickable prototype hand-off (R1)

- Layer: web (design)
- Contract: a claude.ai Design artifact in the Pebble direction (ADR-0035, ADR-0009), scope: the settings form with the zone combobox and live local time, the zone-change preview and the conflict banner (login page and other states are in the screens document). `docs/design/web-settings-prototype.md` records the artifact URL, the stakeholder comments and their outcome, Marco's approval, and any token value that differs from the ADR-0035 starting values.
- Files: `docs/design/web-settings-prototype.md`
- Depends on: —
- Parallel: yes (does not gate the backend)
- Guardrails: guardrail-a11y, guardrail-tailwind
- Criteria:
  1. Given the artifact, When walked through at 375 and 1280 px, Then the zone is the first field, typing shows options with local time and the live paragraph "In Amsterdam it is 21:42 right now.", and a zone change shows the preview line (AC-28) (type: happy; level: review).
  2. Given the conflict banner in the artifact, When shown, Then every edited field has "Use mine" and "Keep Telegram's" with both values visible (AC-28) (type: happy; level: review).
  3. Given the artifact at 320 px and at 200 % text size, When checked, Then there is no horizontal scroll and the two buttons stack with Save first (AC-22) (type: edge; level: review).
  4. Given the measured text, border and focus pairs of the artifact in light and dark, When recorded in the hand-off, Then each text pair is at least 4.5:1 and each border, focus ring and control edge at least 3:1 (AC-22, AC-23) (type: a11y; level: review).
  5. Given every comment on the artifact, When the hand-off is read, Then each has an outcome (done, rejected with reason, or moved to a later unit) and Marco's approval is recorded with the date (ADR-0009) (type: happy; level: review).
  6. Given the artifact content, When checked, Then it uses sample values only: no real e-mail, no real zone of Marco, no analytics, and it is shared by invitation only (data classification: the time zone reveals travel) (type: security; level: review).
  7. Given the hand-off file, When `node scripts/docs.mjs check` runs, Then it passes and links the artifact and the screens document (type: happy; level: ci).

### U-web-settings-02: Pebble tokens and contrast test (R1)

- Layer: web
- Contract: `packages/tokens/tokens.json` replaces the placeholder with Pebble through `design-tokens-bridge`: semantic colours with a light and a dark value (surface, surface-raised, text, text-muted, primary, primary-contrast, danger, success, focus, border), fonts (Bricolage Grotesque for headings, Figtree for text, with system fallback stacks), radii (control 14 px, card 24 px, pill), soft shadow, spring motion of about 200 ms, spacing. `build.mjs` regenerates `tokens.css` and `theme.native.json`. The contrast test covers text pairs at 4.5:1 and border, focus and control pairs at 3:1. How the fonts are loaded is not decided here (Decisions needed D-2).
- Files: `packages/tokens/tokens.json`, `packages/tokens/tokens.css` (generated), `packages/tokens/theme.native.json` (generated), `packages/tokens/contrast.test.mjs`, `packages/tokens/build.mjs`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-tailwind, guardrail-a11y
- Criteria:
  1. Given `tokens.json`, When validated, Then every colour has a light and a dark value, names are semantic and the placeholder description is gone (type: happy; level: unit).
  2. Given the text pairs (text on surface and surface-raised, text-muted on surface and surface-raised, primary-contrast on primary, danger and success on surface-raised) in both modes, When measured, Then each is at least 4.5:1 (AC-22) (type: a11y; level: unit).
  3. Given border, focus ring and control edge against their adjacent surface in both modes, When measured, Then each is at least 3:1 (AC-23) (type: a11y; level: unit).
  4. Given a token that fails by a hair, When the test runs, Then it fails and names the pair and the mode (type: error; level: unit).
  5. Given a changed `tokens.json` without regenerated files, When `node packages/tokens/build.mjs --check` runs, Then it fails (type: error; level: ci).
  6. Given the motion tokens, When read, Then the longest duration is at most 250 ms and a reduced-motion value of 0 exists (type: edge; level: unit).
  7. Given `apps/web/src`, When searched for hex colours, `rgb(` and arbitrary Tailwind values, Then there is no hit outside the tokens package (guardrail-tailwind) (type: edge; level: ci).
  8. Given the `web` CI job, When read, Then it runs the tokens build check and `node --test` of the package (type: happy; level: ci).

### U-web-settings-03: Backend image with the shared package (R1)

- Layer: infra
- Contract: `backend` depends on `packages/schedule-policy` as a uv path dependency (lockfile updated); `backend/Dockerfile` is built from the repo root, copies the package and sets `PYTHONTZPATH` to the pinned `tzdata` wheel as in the agent image (ADR-0028); compose (`api`, `api-dev`, `api-test`) and the `images` CI job use the repo-root context. No code imports the package yet.
- Files: `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`, `backend/Dockerfile.dockerignore`, `compose.yaml`, `.github/workflows/ci.yml`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-docker, guardrail-compose
- Criteria:
  1. Given a clean `uv sync --frozen` in `backend`, When `import schedule_policy` runs, Then it works (type: happy; level: unit).
  2. Given a docker build from the repo root, When the image starts, Then `from schedule_policy.policy import DEFAULT_POLICY` works (type: happy; level: image).
  3. Given the image, When `zoneinfo` resolves `Pacific/Kiritimati`, Then the data comes from the pinned `tzdata` wheel; a test fails when `/usr/share/zoneinfo` would win (ADR-0028) (type: edge; level: image).
  4. Given the build context, When the image is built, Then `.env`, `.git` and `node_modules` are excluded (type: security; level: image).
  5. Given the Trivy scan and hadolint of the `images` job, When run on the new image, Then no new High or Critical finding and no hadolint warning (type: security; level: ci).
  6. Given `docker compose --profile dev config` and `--profile test config`, When rendered, Then the `api-dev` and `api-test` builds still resolve and the existing backend suite is green (type: happy; level: ci).

### U-web-settings-04: Backend foundation: configuration, start-up check, Clock and IdSource (R1)

- Layer: backend
- Contract: `Settings` gains issuer, client id, client secret, allowed `sub`, public origin, subject-hash key, CSRF key, database URL, idle (30 min) and absolute (12 h) limits, flow cap, trusted-proxy CIDR and hop count, rate and body limits (30 a minute, 8192 bytes). `validate_startup(settings)` raises `ConfigurationError` naming the key, never the value. `Clock.now() -> datetime` (aware UTC; `SystemClock`, test `FakeClock`) and `IdSource` (`token(nbytes)`, `request_id()`; test `FakeIds`). `create_app(settings, *, clock, ids)` calls the check at start.
- Files: `backend/app/config.py`, `backend/app/startup.py`, `backend/app/clock.py`, `backend/app/ids.py`, `backend/app/main.py`, `backend/tests/` (conftest helpers, `test_startup.py`)
- Depends on: U-web-settings-03
- Parallel: yes (with U-06)
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-oauth2-oidc
- Criteria:
  1. Given a complete valid configuration, When checked, Then there is no error (type: happy; level: unit).
  2. Given an empty allowed `sub`, When the app starts, Then it refuses and the message names `ALLOWED_SUB` and no value (AC-4, W-1) (type: error; level: api).
  3. Given an `http://` issuer, When the app starts, Then it refuses (AC-4, W-1) (type: error; level: api).
  4. Given a missing or empty client secret, When the app starts, Then it refuses (AC-4, W-1) (type: error; level: api).
  5. Given a public origin that is not `https` or a redirect URI that is not origin plus `/auth/callback`, When checked, Then it refuses (type: error; level: unit).
  6. Given a subject-hash key or CSRF key shorter than 32 bytes, or the two keys equal, When checked, Then it refuses (W-4, W-13) (type: security; level: unit).
  7. Given the test and development environments, When the settings are read, Then no setting turns the check off (type: security; level: unit).
  8. Given a `FakeClock`, When the app is created with it, Then every time-dependent helper reads it and none reads the system clock (a test patches `datetime` to raise) (type: happy; level: api).
  9. Given the production `IdSource`, When it makes a token, Then it has at least 256 bits from `secrets`; the fake is deterministic (type: security; level: unit).
  10. Given a failing start, When logs are captured, Then no secret, key or issuer secret part appears (type: security; level: api).

### U-web-settings-05: HTTP surface: errors, headers, request id and route inventory (R1)

- Layer: backend
- Contract: `application/problem+json` handlers for 401, 403 (one body for CSRF, Origin and a write without session), 404, 405, 413, 415, 429 (with `Retry-After`) and 500 with a generic title; middleware adds `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` to every response and the CSP (`script-src 'self'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`) to every HTML response the api serves; the request id comes from `IdSource`, is returned as `X-Request-Id` and a client value is never accepted; `/docs`, `/redoc`, `/openapi.json` are off in production; the route inventory test allows exactly the design's path allow-list (`/auth/login`, `/auth/callback`, `/auth/logout`, `/api/session`, `/api/settings`, `/api/places`, and the probes) and rejects anything else; every route declares `public` or `session`.
- Files: `backend/app/main.py`, `backend/app/errors.py`, `backend/app/middleware.py`, `backend/app/core/security.py`, `backend/tests/test_route_inventory.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-04
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given an unhandled exception, When the response is built, Then the body is a generic 500 problem without class, message or trace (AC-15, W-6) (type: security; level: api).
  2. Given an unknown path, When requested, Then 404 with a generic problem (AC-15) (type: error; level: api).
  3. Given any response, When inspected, Then it carries `no-store`, `nosniff` and `no-referrer` (AC-14, W-5) (type: security; level: api).
  4. Given an HTML response served by the api, When inspected, Then the CSP has exactly `script-src 'self'`, `frame-ancestors 'none'`, `base-uri 'self'` and `form-action 'self'` and no `unsafe-inline` (AC-14, W-5) (type: security; level: api).
  5. Given a request with `X-Request-Id: attacker`, When answered, Then the response id is the one from `IdSource` (W-13) (type: security; level: api).
  6. Given production settings, When `/docs`, `/redoc` and `/openapi.json` are requested, Then 404 (AC-19, W-6) (type: security; level: api).
  7. Given a route outside the allow-list, When the inventory test runs, Then it fails naming the path; a route without a `public` or `session` marker also fails (AC-15) (type: security; level: unit).
  8. Given `uv run python -m app.export_openapi --check`, When run, Then it passes and the exported paths are a subset of the allow-list (AC-15) (type: happy; level: ci).
  9. Given a 429 or 413 problem, When built, Then `Retry-After` (429) is an integer and the body names no limit value or client (type: edge; level: api).

### U-web-settings-06: Migration 0008: web_auth, web guard line, contract version, notice record (R1)

- Layer: backend (database; agent migration chain)
- Contract: migration `0008` in `agents/mail-triage/migrations`: schema `web_auth` with `login_flow` (hashed id, state, nonce, PKCE verifier, return path, `expires_at`), `session` (hashed id, hashed subject, e-mail for display, `last_seen_at`, `absolute_expires_at`), `security_event` (kind, issuer, hashed subject, request id, client window, no free text) and `web_lock` (single row); the web line in the guard of 0006 (`session_user = 'web_settings_runtime'` gives channel `web`, `updated_by` must match `^web:[0-9a-f]{32}$`, `version = old + 1`); the cursor for web notices in `poll_state`; the notice token record table; `settings.contract_version()`; every new function revoked from `PUBLIC`. The runtime roles' grants are not here (U-07).
- Files: `agents/mail-triage/migrations/versions/0008_web_auth.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/tests/db/test_web_auth_migration.py`, `agents/mail-triage/tests/db/test_settings_migration.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given revision 0007 with settings data, When migrated to 0008, Then the `web_auth` tables, the cursor column and the notice table exist, data is unchanged and models match the schema (no drift) (type: happy; level: db).
  2. Given 0008, When downgraded, Then the schema, tables, column, function and the web guard line are gone, the 0006 guard works as before, and upgrade again is clean (type: edge; level: db).
  3. Given a write by session user `web_settings_runtime` (created in the test), When it updates the row, Then `updated_via` is `web` and the audit record has `db_role` web (AC-9, W-10) (type: happy; level: db).
  4. Given a write by the web role whose `updated_by` is `telegram:1`, `web:` plus 31 hex, upper-case hex or empty, When executed, Then SQLSTATE 42501 (AC-17, W-10) (type: security; level: db).
  5. Given the web role and a version that is not old plus one, or a claimed `updated_via` of `telegram`, When executed, Then 42501 (AC-17) (type: security; level: db).
  6. Given the 0006 guard tests for the agent role and the owner, When run, Then they pass unchanged (type: happy; level: db).
  7. Given `settings.contract_version()`, When called, Then it returns the integer constant of this schema; and the ACL of every function added by 0008 has no `PUBLIC` execute (W-8) (type: security; level: db).
  8. Given `security_event` and `login_flow`, When their columns are inspected, Then kinds are a CHECK-constrained set, hashes are fixed-length, and there is no unbounded text column (W-13) (type: security; level: db).
  9. Given `web_lock`, When a second row is inserted, Then it is refused (single row) (ADR-0033) (type: edge; level: db).
  10. Given the notice token record, When two records with the same token are inserted, Then the second is refused and the token column is unique and random-length constrained (ADR-0033) (type: edge; level: db).

### U-web-settings-07: Grants and the web role in the migrate job (R1)

- Layer: backend (database)
- Contract: `grants.sql` (still the one source) gains `web_settings_runtime`: `SELECT` on `settings.schedule`; `INSERT` and `UPDATE` limited to the columns `(id,) zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by`; execute on `settings.contract_version()`; on `web_auth`: `login_flow` insert/select/delete, `session` insert/select/update/delete, `security_event` insert/select, `web_lock` select; nothing on `public`, nothing on `settings_change`. The agent role gains `INSERT, UPDATE, SELECT` on `web_auth.web_lock` and nothing else in `web_auth`. `migrate.py` creates the roles from a list (agent runtime role and web role) with the SCRAM, no-membership and no-replication rules of ADR-0030; `WEB_ROLE_PASSWORD` is a new setting.
- Files: `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/db/migrate.py`, `agents/mail-triage/app/settings.py`, `agents/mail-triage/tests/db/test_web_role_grants.py`, `agents/mail-triage/tests/db/test_migrate_job.py`
- Depends on: U-web-settings-06
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest, guardrail-python
- Criteria:
  1. Given the web role after migrate, When it selects and updates the allowed columns of `settings.schedule` and inserts the first row, Then each works (type: happy; level: db).
  2. Given the web role, When it updates `updated_at`-like or any column outside the list, or deletes or truncates `settings.schedule`, Then 42501 (AC-17) (type: security; level: db).
  3. Given a parametrised list of `mail_item`, `alert`, `draft`, `oauth_token`, `audit_log`, `poll_state`, `catchup_state`, `overview_log`, `conversation`, `alembic_version`, When the web role selects, Then 42501 each (AC-17, W-8) (type: security; level: db).
  4. Given `settings.settings_change`, When the web role selects, inserts, updates, deletes or truncates, Then 42501 (AC-17) (type: security; level: db).
  5. Given the web role, When it runs `CREATE TABLE`, `ALTER`, `DROP`, or `SET session_replication_role`, Then 42501 (AC-17) (type: security; level: db).
  6. Given the exact rights on `web_auth`, When the web role updates `web_lock`, deletes `security_event` or updates `login_flow`, Then 42501 (ADR-0033) (type: security; level: db).
  7. Given the agent role, When it writes `web_auth.web_lock` it works, and when it reads or writes `session`, `login_flow` or `security_event` it gets 42501 (ADR-0033) (type: security; level: db).
  8. Given the migrate job with a list of two roles and two passwords, When it runs, Then both roles exist with SCRAM verifiers computed client side, `NOREPLICATION NOBYPASSRLS`, no membership, and no statement the server received contains a clear password (ADR-0030) (type: security; level: db).
  9. Given a missing `WEB_ROLE_PASSWORD`, or a web role that has a membership, When the job runs, Then it fails (exit 6 for the membership) naming the key or role, not the value (type: error; level: db).
  10. Given `grants.sql` run twice, When compared, Then the same grants result (type: edge; level: db).

### U-web-settings-08: Database access and readiness (R1)

- Layer: backend
- Contract: async engine and session factory for the web role (`sqlalchemy[asyncio]`, `asyncpg`); in production the URL must have `sslmode=verify-full` (start-up check); statement timeout from settings; `/readyz` compares `settings.contract_version()` with the expected constant instead of the agent's Alembic head; start-up removes expired `login_flow` and `session` rows using `Clock`; the shared DB test fixture (applies the agent chain, `grants.sql`, connects as the web role).
- Files: `backend/app/db.py`, `backend/app/routers/health.py`, `backend/app/startup.py`, `backend/pyproject.toml`, `backend/tests/db/conftest.py`
- Depends on: U-web-settings-04, U-web-settings-06, U-web-settings-07
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-fastapi
- Criteria:
  1. Given a migrated database, When `/readyz` is called, Then 200 (type: happy; level: db).
  2. Given a database whose `contract_version()` differs, When `/readyz` is called, Then 503 with a generic body (type: error; level: db).
  3. Given the database is down, When `/readyz` is called, Then 503 and the log has the error class and SQLSTATE only, never the URL or password (type: error; level: db).
  4. Given production settings with `sslmode=disable`, `require` or none, When the app starts, Then it refuses naming `DATABASE_URL` (W-8, W-9) (type: security; level: unit).
  5. Given expired and valid rows in `login_flow` and `session` and a `FakeClock`, When the app starts, Then only the expired rows are removed (type: edge; level: db).
  6. Given the source tree, When searched for `now()` and `CURRENT_TIMESTAMP` in SQL text, Then there is no hit (the clock is a parameter) (type: edge; level: unit).
  7. Given a statement slower than the configured timeout, When run, Then it is cancelled and the request ends 503 (W-7) (type: error; level: db).
  8. Given the fixture, When two tests run in a row, Then each starts from a clean schema state (type: edge; level: db).

### U-web-settings-09: Security events and log hygiene (R1; the alert is R2)

- Layer: backend
- Contract: `SecurityEvents.record(kind, issuer, subject, request_id, client)` writes `web_auth.security_event`; kinds `signin_refused` (valid token, wrong account), `signin_failed` (protocol failure), `session_start`, `session_end`, `csrf_refused`, `rate_limited`; `subject_digest(key, sub) -> 32 hex` (HMAC, also the `updated_by` value `web:<32 hex>`); one entry per kind, client and window (`floor(clock.now() / 60)`); a log line per recorded event; the uvicorn access log is off, request logging has no query string, and the `httpx`, `httpcore` and `authlib` loggers are pinned to WARNING.
- Files: `backend/app/security_events.py`, `backend/app/logging_setup.py`, `backend/app/main.py`, `backend/Dockerfile`, `backend/tests/test_security_events.py`
- Depends on: U-web-settings-05, U-web-settings-07, U-web-settings-08
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-oauth2-oidc
- Criteria:
  1. Given a refused sign-in with an unknown `sub`, When recorded, Then the row has kind, issuer, the digest of the `sub` and the request id, and the raw `sub` is nowhere in the database or the log (AC-20, W-13) (type: security; level: db).
  2. Given ten identical refusals from one client in one window, When recorded, Then one row exists; a refusal after the `FakeClock` crosses the window adds a second (AC-20) (type: edge; level: db).
  3. Given two different kinds from one client in one window, When recorded, Then both are kept (type: edge; level: db).
  4. Given a recorded event, When the log is captured, Then one line has result, issuer, digest and request id and no token, code or `sub` (AC-20, W-13) (type: security; level: api).
  5. Given `GET /auth/callback?code=SECRET&state=S`, When served, Then no captured log line contains `code=`, `SECRET`, `state=` or a `?` (AC-20, W-13) (type: security; level: api).
  6. Given the image command, When read, Then the access log is disabled (no `--access-log`) (AC-20) (type: security; level: ci).
  7. Given the app is created, When the loggers are read, Then `httpx`, `httpcore` and `authlib` are at WARNING (type: security; level: unit).
  8. Given a provider error with an `error_description`, When handled, Then the text is in no log line, event or response (type: security; level: api).
  9. Given `subject_digest`, When called with two keys or two subs, Then results differ, are 32 lower-case hex characters and are stable for the same input (type: unit; level: unit).
  10. Given the event insert fails, When a refusal is answered, Then the refusal still returns 403 and the log has the error class only (type: error; level: db).

### U-web-settings-10: ID token validator, discovery and fake provider (R1)

- Layer: backend
- Contract: `discover(issuer)` fetches metadata only from the configured `https` issuer and refuses when the metadata `issuer` differs; `validate_id_token(token, *, expected, now)` with Authlib/joserfc, algorithms pinned to RS256 and ES256, checks signature through the issuer's JWKS (refreshed at most once per interval on an unknown `kid`), `iss`, `aud`, `azp`, `exp` against `now`, `nonce`; `Identity` compares the exact pair (issuer, `sub`) and ignores the e-mail. A pure module `app/auth/identity.py` holds the comparison. `tools/mock-oidc` is an ASGI fake provider (configurable key and claims, tokens issued from the same `Clock`, a non-interactive sign-in by `login_hint` for the allowed user and a second user) used by the in-process tests and, in U-31, as a container.
- Files: `backend/app/auth/discovery.py`, `backend/app/auth/token.py`, `backend/app/auth/identity.py`, `tools/mock-oidc/mock_oidc/provider.py`, `backend/tests/auth/test_token.py`
- Depends on: U-web-settings-04
- Parallel: yes (with U-06 to U-09)
- Guardrails: guardrail-oauth2-oidc, guardrail-fastapi
- Criteria:
  1. Given the fake provider's token for the allowed account, When validated, Then it is accepted (type: happy; level: unit).
  2. Given a bad signature, an expired token (clock at `exp`), a wrong issuer, a wrong audience, a wrong `azp` and a wrong nonce, When validated, Then each is refused, one test each (AC-5, W-2) (type: security; level: unit).
  3. Given `alg: none`, HS256 signed with the public key, and an unknown `kid`, When validated, Then refused (W-2) (type: security; level: unit).
  4. Given an unknown `kid`, When it recurs inside the refresh interval, Then the JWKS is fetched once, not per request (type: edge; level: unit).
  5. Given discovery metadata whose `issuer` differs from the configured one, or an `http` issuer, When fetched, Then refused and nothing is followed (W-2) (type: security; level: unit).
  6. Given a token with the right `sub` from another issuer, the right e-mail with another `sub`, or only an unverified e-mail claim, When the identity is compared, Then `NotAllowed` (AC-3, W-1) (type: security; level: unit).
  7. Given the allowed pair with a changed e-mail claim, When compared, Then still allowed (e-mail is display only) (type: edge; level: unit).
  8. Given an exception raised by the library with a provider description, When surfaced, Then the description is not in the message (type: security; level: unit).
  9. Given the fake provider and `login_hint`, When a token is requested for the allowed user and for the second user, Then each carries its own `sub` and the fake `Clock` times (type: happy; level: api).

### U-web-settings-11: Login flow: GET /auth/login (R1)

- Layer: backend
- Contract: `GET /auth/login?return_to=` checks the limit hook, creates a `web_auth.login_flow` row (state, nonce, PKCE verifier, return path; expired rows removed on insert; capped number of open rows), sets `__Host-login` (random id, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, 10 minutes) and answers 302 to the provider (S256, scope exactly `openid email profile`, exact redirect URI). Any `return_to` other than `/settings` becomes `/settings`. A pure function `safe_return_to(value) -> str` holds the allow-list.
- Files: `backend/app/auth/login_flow.py`, `backend/app/auth/return_to.py`, `backend/app/routers/auth.py`, `backend/tests/auth/test_login.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-08, U-web-settings-09, U-web-settings-10
- Parallel: no
- Guardrails: guardrail-oauth2-oidc, guardrail-fastapi, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given `GET /auth/login`, When answered, Then 302 to the discovered authorization endpoint with `response_type=code`, the client id, the exact redirect URI, `code_challenge_method=S256`, `state` and `nonce` (AC-6, W-2) (type: happy; level: api).
  2. Given the response, When the cookie is read, Then `__Host-login` has `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, 10 minutes, and a random id that is not the state (AC-6, W-2) (type: security; level: api).
  3. Given `return_to` of `https://evil.example`, `//evil.example`, `/\evil`, `javascript:alert(1)`, `/settings/../x` and `/other`, When processed, Then the stored return path is `/settings`; only `/settings` is kept (AC-6, W-2) (type: security; level: unit).
  4. Given the request, When the scope is read, Then it is exactly `openid email profile`; a Gmail or Calendar scope never appears (ADR-0024, non-goal) (type: security; level: api).
  5. Given the maximum number of open flows, When another sign-in starts, Then 429 and no row is written (AC-16, W-7) (type: security; level: db).
  6. Given rows older than 10 minutes by the `FakeClock`, When a flow is inserted, Then they are removed (type: edge; level: db).
  7. Given the state, nonce and verifier, When read from the database, Then they are server-side only and never in a URL other than the provider redirect (state and challenge only) (W-2) (type: security; level: api).
  8. Given discovery fails, When `/auth/login` is called, Then a generic error page, no redirect and a `signin_failed` event (type: error; level: api).

### U-web-settings-12: Sessions: store, cookie, expiry and lock check (R1)

- Layer: backend
- Contract: `SessionStore.create(subject_digest, email, now) -> (cookie_value, Session)` (new random id each time; only the hash is stored), `get(cookie_value, now)`, `touch`, `delete`; `session_cookie(value)` builds `__Host-session` (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`); `require_session` dependency (marker `session`); pure module `app/auth/expiry.py` (`idle_expired`, `absolute_expired`: 30 min idle, 12 h absolute); while `web_auth.web_lock` is set every session lookup answers 401 and deletes the sessions.
- Files: `backend/app/auth/session.py`, `backend/app/auth/expiry.py`, `backend/app/core/security.py`, `backend/tests/auth/test_session.py`
- Depends on: U-web-settings-05, U-web-settings-08, U-web-settings-09
- Parallel: yes (with U-10, U-11)
- Guardrails: guardrail-fastapi, guardrail-oauth2-oidc, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a created session, When the cookie is built, Then name `__Host-session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, 256-bit random value (AC-7, W-3) (type: security; level: unit).
  2. Given a session last seen at 14:00:00, When asked at 14:29:59 and 14:30:00, Then valid, then expired (AC-7) (type: edge; level: unit).
  3. Given activity every 20 minutes, When asked after 12 h 00 min 00 s, Then expired by the absolute limit; one second earlier valid (AC-7) (type: edge; level: unit).
  4. Given two sign-ins, When both create sessions, Then the ids differ, and a cookie presented before sign-in is never adopted (AC-7, W-3) (type: security; level: db).
  5. Given the database, When read as the owner, Then only the hash of the id and the digest of the subject are stored (W-3) (type: security; level: db).
  6. Given no cookie, an unknown cookie or an expired session, When a protected route is called, Then 401 with the generic body (AC-2) (type: error; level: api).
  7. Given `web_lock` set, When a valid session calls a protected route, Then 401, and the sessions are deleted (AC-27, ADR-0033) (type: security; level: db).
  8. Given each request, When it is authorised, Then `last_seen_at` moves to the clock's now (type: happy; level: db).
  9. Given `idle_expired` and `absolute_expired`, When mutated in review, Then boundary rows exist for 29:59, 30:00, 11:59:59 and 12:00:00 (kills `<` vs `<=`) (type: edge; level: unit).

### U-web-settings-13: Callback: GET /auth/callback (R1)

- Layer: backend
- Contract: `GET /auth/callback?code&state` deletes the flow row by cookie id with `DELETE ... RETURNING` (single use), compares `state`, exchanges the code (exact redirect URI and verifier), validates the ID token (U-10), compares the exact pair, checks the web lock, creates the session (U-12), sets `__Host-session`, clears `__Host-login` and answers 303 to the stored return path. Failures are static pages served by the api with the CSP: 400 "Sign-in failed, try again", 403 "This account is not allowed for this app"; both clear `__Host-login`. Every outcome writes a security event. The refusal surface is Decisions needed D-5.
- Files: `backend/app/routers/auth.py`, `backend/app/auth/callback.py`, `backend/app/auth/pages.py`, `backend/tests/auth/test_callback.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-11, U-web-settings-12
- Parallel: no
- Guardrails: guardrail-oauth2-oidc, guardrail-fastapi
- Criteria:
  1. Given a valid callback for the allowed account, When processed, Then 303 to `/settings`, a new `__Host-session`, `__Host-login` cleared and a `session_start` event (AC-7) (type: happy; level: api).
  2. Given a wrong `state`, When processed, Then 400, the 400 page, no session, `__Host-login` cleared (AC-5, W-2) (type: security; level: api).
  3. Given a `state` cookie of another browser (another flow's id, or none), When processed, Then 400 and no session (AC-5, W-2) (type: security; level: api).
  4. Given the same callback twice, or after 10 minutes by the `FakeClock`, When processed, Then the second and the late one get 400 (single use, expiry) (AC-5) (type: security; level: db).
  5. Given a wrong nonce, a bad signature, an expired token, a wrong issuer, a wrong audience and a wrong `azp`, When the callback is processed end to end, Then each is refused with 400 and no session, one test each (AC-5) (type: security; level: api).
  6. Given the right `sub` from another issuer, the right e-mail with another `sub`, or an unverified e-mail only, When processed, Then 403 with "This account is not allowed for this app", no session and a `signin_refused` event (AC-3, AC-24, W-1) (type: security; level: api).
  7. Given the token request, When captured at the fake provider, Then the redirect URI is the exact registered one, the code verifier is sent and no client secret appears in a URL (AC-6, W-2) (type: security; level: api).
  8. Given `web_lock` set, When the allowed account calls back, Then 403 and no session (AC-27, ADR-0033) (type: security; level: db).
  9. Given the 400 and 403 pages, When inspected, Then they have the CSP, `no-store`, no provider text and no code, and a protocol failure writes `signin_failed`, not `signin_refused` (AC-15, AC-20, W-6) (type: security; level: api).
  10. Given the provider's token endpoint times out or returns an error, When processed, Then the 400 page and a `signin_failed` event; no session (type: error; level: api).

### U-web-settings-14: CSRF, Origin, /api/session and logout (R1)

- Layer: backend
- Contract: the CSRF token is `HMAC(csrf_key, session_id)` compared in constant time (pure module `app/auth/csrf.py`); `GET /api/session` (session, `Sec-Fetch-Site` same-origin) returns `{email, csrfToken, idleExpiresAt, absoluteExpiresAt}`; `require_csrf` dependency (marker `csrf`) needs `X-CSRF-Token` and `Origin` equal to the public origin (a missing `Origin` or `Sec-Fetch-Site: cross-site` is refused with the one 403 body); `POST /auth/logout` (session, CSRF, Origin) answers 204, deletes the session and clears the cookie; a GET on a write route answers 405; no CORS.
- Files: `backend/app/auth/csrf.py`, `backend/app/routers/session.py`, `backend/app/routers/auth.py`, `backend/app/core/security.py`, `backend/tests/auth/test_csrf.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-12, U-web-settings-13
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-oauth2-oidc
- Criteria:
  1. Given a session id, When the token is derived, Then it equals the HMAC, differs for another session id and is compared in constant time (W-4) (type: security; level: unit).
  2. Given a same-origin `GET /api/session`, When answered, Then email, token and both expiry times, and no other field (AC-15) (type: happy; level: api).
  3. Given `Sec-Fetch-Site: cross-site` on `GET /api/session`, When answered, Then 403 and no token (AC-8, W-4) (type: security; level: api).
  4. Given a write without the token, with a wrong token, and with a token of another session, When sent, Then 403 with the same body and nothing changes (AC-8, W-4) (type: security; level: api).
  5. Given a valid token with a wrong, missing or `null` `Origin`, or `Sec-Fetch-Site: cross-site`, When sent, Then 403 (AC-8, W-4) (type: security; level: api).
  6. Given a GET on a write route, When sent, Then 405 (AC-8) (type: security; level: api).
  7. Given a valid logout, When sent, Then 204, the session row is gone, the cookie is cleared and the old cookie then gets 401 (AC-7) (type: happy; level: db).
  8. Given a logout without the token, When sent, Then 403 and the session stays valid (AC-8) (type: security; level: api).
  9. Given two tabs of one session, When both use the token, Then both work (design delta W-4) (type: edge; level: api).
  10. Given a preflight `OPTIONS` or any response, When inspected, Then there is no `Access-Control-Allow-*` header; a CSRF refusal writes `csrf_refused` once per client and window (AC-8, AC-20, W-4) (type: security; level: api).
  11. Given the route inventory, When read, Then every `POST` and `PUT` operation has both the `session` and the `csrf` marker; one without fails (AC-15) (type: security; level: unit).

### U-web-settings-15: In-process rate and body limits (R1)

- Layer: backend
- Contract: ADR-0034. Pure module `app/limits.py` (`window_key(now) = floor(now / 60)`, fixed-window counter per client and bucket `signin` / `api`, bounded memory) and `app/clientaddr.py` (`client_key(peer, xff, trusted_cidrs, hops)` returns the address the last trusted proxy appended; any other peer is keyed by its own address). The check runs before any `login_flow` insert. 30 requests a minute (configurable), body 8192 bytes (413, also for chunked bodies without a length).
- Files: `backend/app/limits.py`, `backend/app/clientaddr.py`, `backend/app/middleware.py`, `backend/app/config.py`, `backend/tests/test_limits.py`
- Depends on: U-web-settings-05, U-web-settings-09, U-web-settings-11
- Parallel: yes (with U-14)
- Guardrails: guardrail-fastapi
- Criteria:
  1. Given 30 requests to `/auth/login` in one window, When the 31st arrives, Then 429 with an integer `Retry-After`, and in the next window it passes again (AC-16, W-7) (type: security; level: api).
  2. Given the `api` bucket on `/api/settings`, When the same client exceeds it, Then 429, and the `signin` bucket is unaffected (AC-16) (type: edge; level: api).
  3. Given the limit is exceeded on `/auth/login`, When the database is read, Then no `login_flow` row was written for the refused requests (AC-16, W-7) (type: security; level: db).
  4. Given `X-Forwarded-For: spoof, real` where the last trusted proxy appended `real`, When keyed, Then the key is `real`; a spoofed leftmost value never opens a fresh bucket; a peer outside the trusted CIDR is keyed by its own address (W-7) (type: security; level: unit).
  5. Given a body of 8192 and 8193 bytes, and a chunked body over the limit, When sent to a write route, Then accepted, 413, 413, and the body is not parsed (AC-16) (type: edge; level: api).
  6. Given a flood from one client in one window, When it is refused, Then exactly one `rate_limited` event exists for that client and window (AC-20, W-13) (type: security; level: db).
  7. Given limits lowered or raised through settings, When read, Then they take effect (tests use 3; the prod-like profile raises them) (type: happy; level: api).
  8. Given many distinct clients over many windows, When counters are held, Then old windows are dropped and memory stays bounded (W-7) (type: edge; level: unit).
  9. Given `window_key`, When mutated in review, Then boundary rows exist at 59.9 s, 60.0 s and 60.1 s (type: edge; level: unit).

### U-web-settings-16: Settings write repository (R1)

- Layer: backend (database)
- Contract: `SettingsRepository.read() -> StoredSettings | None`; `write(values, expected_version, subject_digest) -> StoredSettings` as about 40 lines of SQLAlchemy Core: one `UPDATE ... WHERE version = :v RETURNING`, or `INSERT ... ON CONFLICT DO NOTHING` at version 0; `VersionConflict` carries the current row. The guard sets the channel and the audit trigger records the change in the same transaction.
- Files: `backend/app/settings_repo.py`, `backend/tests/db/test_settings_repo.py`, `backend/tests/db/test_contract_fixture.py`
- Depends on: U-web-settings-06, U-web-settings-07, U-web-settings-08
- Parallel: yes (with U-10 to U-15)
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pydantic
- Criteria:
  1. Given no row, When read, Then `None`; When written at version 0, Then version 1 and the row exists; a second writer at version 0 gets `VersionConflict` (AC-9, AC-11) (type: happy; level: db).
  2. Given a write at version 1, When committed, Then version 2, exactly one `settings_change` record with `db_role` of the web role, channel `web` and `updated_by` of the form `web:<32 hex>` (AC-9, W-10) (type: happy; level: db).
  3. Given two sessions that read the same version and an explicit barrier, When both write, Then exactly one succeeds, the other gets `VersionConflict` with the current row, one audit record exists (AC-11, W-12) (type: edge; level: db).
  4. Given a stale version, When written, Then `VersionConflict`, nothing changes (AC-11) (type: error; level: db).
  5. Given the audit trigger fails (a test replaces its function with one that raises), When a write runs, Then the whole write is rolled back and the error is not a success (AC-17) (type: security; level: db).
  6. Given a write that sets `version` to old plus 2, When executed through the role, Then 42501 (AC-17) (type: security; level: db).
  7. Given the shared fixture `packages/schedule-policy/contract/settings_cases.json`, When run through the repository, Then outcomes match the package and the agent (AC-26) (type: happy; level: db).
  8. Given a zone value of `'; drop table settings.schedule; --`, When written, Then the statement is parameterised, the database CHECK refuses it and nothing changes (AC-10) (type: security; level: db).
  9. Given a failure path, When logs are captured, Then no record contains `Pacific/Kiritimati` or a subject (AC-33 of `adjustable-quiet-hours`) (type: security; level: db).

### U-web-settings-17: Settings API routes and the RULES export (R1)

- Layer: backend
- Contract: `GET /api/settings` (session) returns `Settings` `{values: {timeZone, quietStart, quietEnd, overviewAt, remindAt}, version, updatedAt, updatedVia}` with `HH:MM` strings and `additionalProperties: false`, defaults with `version: 0` when no row; `PUT /api/settings` (session, CSRF, Origin) takes `{values, version}`: format check, `schedule_policy.validate`, `repository.write`; 200 `Settings`, 409 with the current `Settings`, 422 `problems: [{field, rule, value, example}]`, 415. `schedule_policy` exports `RULES` (the list of rule ids); `app/settings_fields.py` maps every rule to a field (`quiet_window_*` to start and end, `overview_in_quiet_hours`, `remind_in_quiet_hours`, `zone_unknown`). `updatedAt` and `updatedVia` at version 0: Decisions needed D-8.
- Files: `packages/schedule-policy/schedule_policy/policy.py`, `packages/schedule-policy/schedule_policy/__init__.py`, `backend/app/routers/settings.py`, `backend/app/settings_fields.py`, `backend/tests/test_settings_api.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-12, U-web-settings-14, U-web-settings-15, U-web-settings-16
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-oauth2-oidc
- Criteria:
  1. Given a stored row, When `GET /api/settings`, Then the four values as `HH:MM`, the version, `updatedAt` and `updatedVia`, and no actor field (AC-1, AC-15) (type: happy; level: api).
  2. Given no row, When `GET`, Then the defaults with `version: 0` (AC-1) (type: edge; level: api).
  3. Given a valid `PUT` at the current version, When sent with session and token, Then 200 with the new `Settings` and the next version (AC-9) (type: happy; level: api).
  4. Given an overview inside the quiet hours, When `PUT`, Then 422 with `field: overviewAt`, the same rule text and example as Telegram, nothing stored (AC-10) (type: error; level: api).
  5. Given `RULES` from the package, When the map is checked, Then every rule has a field; adding a rule to the package without a mapping fails this test (AC-10) (type: edge; level: unit).
  6. Given malformed times (`7pm`, `24:00`, `07:00:30`, a number), an unknown zone, `../etc` and an over-long zone, When `PUT`, Then 422 at the edge or from validation, nothing stored (AC-10) (type: security; level: api).
  7. Given an old version, When `PUT`, Then 409 with the current `Settings` (AC-11) (type: edge; level: api).
  8. Given an extra property in the body or a non-JSON content type, When `PUT`, Then 422 or 415 and nothing stored (AC-15) (type: security; level: api).
  9. Given a zone `<script>alert(1)</script>`, When `PUT`, Then 422 and the body carries it only as a JSON string (AC-14) (type: security; level: api).
  10. Given no session, or a session without the token, When `GET` or `PUT`, Then 401 or 403 and nothing is read or written (AC-2, AC-8) (type: security; level: api).

### U-web-settings-18: Places route (R1)

- Layer: backend
- Contract: `GET /api/places?q=` (session, `api` rate bucket) returns up to 5 `{zone, label, utcOffsetMinutes}` and an optional suggestion from `schedule_policy.places.lookup` (same lookup and aliases as Telegram, ADR-0028); the live local time is computed in the browser. This unit also tightens the route inventory from "subset" to "equals" the allow-list.
- Files: `backend/app/routers/places.py`, `backend/tests/test_places_api.py`, `backend/tests/test_route_inventory.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-12, U-web-settings-15
- Parallel: yes (with U-17)
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given `q=New York`, When called, Then a hit for `America/New_York` with label and offset (C-7) (type: happy; level: api).
  2. Given `q=Paris`, When called, Then at most 5 labelled hits; a near-miss `Nwe York` gives the suggestion `New York` (C-7) (type: edge; level: api).
  3. Given the aliases `NYC` and `Wien`, When called, Then the same results as the Telegram lookup (type: edge; level: api).
  4. Given nothing matches, When called, Then an empty list without error (type: edge; level: api).
  5. Given a 65-character `q`, a control character, an emoji and NFC/NFD forms, When called, Then the over-long one is refused with 422 before matching and the others behave as in the package (C-7) (type: security; level: api).
  6. Given the typed text, When logs are captured, Then the query value is in no log line (the zone reveals travel) (W-13) (type: security; level: api).
  7. Given no session, When called, Then 401 (AC-2) (type: security; level: api).
  8. Given more than the `api` bucket in a minute, When called, Then 429 (AC-16) (type: security; level: api).
  9. Given the response model, When checked, Then only `zone`, `label`, `utcOffsetMinutes` and `suggestion` exist, and the route inventory equals the allow-list exactly (AC-15) (type: security; level: unit).

### U-web-settings-19: Web notices in the agent (R1)

- Layer: agent
- Contract: at each run `WebNotice.run(now)` selects `settings_change` records whose `db_role` is not the agent role and whose version (as an integer) is above the cursor in `poll_state`, sends one Telegram notice per change (old and new values, change number, channel `web`, time; no `sub`) with the buttons "Undo" and "Undo and lock web sign-in", records an own token per notice in the notice table (not the conversation row) and advances the cursor. Delivery is at least once. Quiet hours never hold the notice.
- Files: `agents/mail-triage/app/usecases/web_notice.py`, `agents/mail-triage/app/db/pg_web_notice.py`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/app/core/settings_text.py`, `agents/mail-triage/tests/db/test_web_notice.py`
- Depends on: U-web-settings-06, U-web-settings-07
- Parallel: yes
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a web change to version 3, When the agent runs, Then exactly one notice with old values, new values, change number 3, channel web, time, and both buttons (AC-13, W-11) (type: happy; level: agent).
  2. Given the notice was sent, When the agent runs again, Then no second notice (cursor advanced) (AC-13) (type: happy; level: agent).
  3. Given a change made through Telegram (agent role), When the agent runs, Then no web notice (AC-13) (type: edge; level: agent).
  4. Given web changes at versions 9, 10 and 11, When the agent runs, Then three notices in numeric order (10 after 9, never by text) (ADR-0033 item 6) (type: edge; level: agent).
  5. Given the outbox fails once, When the agent runs twice, Then the cursor is not advanced on failure and the notice is sent on the next run; a crash between send and cursor may repeat one notice (AC-13) (type: error; level: agent).
  6. Given a pending Telegram dialogue (the conversation row), When a web notice is sent, Then the conversation row and its message are unchanged (AC-13, ADR-0033 item 1) (type: edge; level: agent).
  7. Given a `FakeClock` inside the quiet hours that the change itself just set, When the agent runs, Then the notice is sent (AC-13, ADR-0033 item 4) (type: edge; level: agent).
  8. Given a web row whose `updated_by` text claims the agent, When selected, Then the notice is still sent because selection uses the server-derived `db_role` (W-11) (type: security; level: db).
  9. Given a notice, When its token record is read, Then it has a random token with an expiry in its own table and none in `conversation` (ADR-0033) (type: security; level: db).
  10. Given a failure path, When logs are captured, Then no zone value, token or `sub` appears (type: security; level: agent).

### U-web-settings-20: Notice buttons: Undo, Undo and lock, unlock command (R1)

- Layer: agent
- Contract: the callbacks `webundo:<token>` and `weblock:<token>` handled through the router: Undo restores the values as they were before the first web change the agent had not yet announced, guarded by the current version, with one audit record (via the agent role); "Undo and lock" first writes `web_auth.web_lock`, then undoes; a Telegram command (name: Decisions needed D-3) clears the lock; only the allowed user and chat.
- Files: `agents/mail-triage/app/usecases/web_notice_actions.py`, `agents/mail-triage/app/db/pg_web_lock.py`, `agents/mail-triage/app/usecases/dispatch.py`, `agents/mail-triage/app/core/settings_text.py`, `agents/mail-triage/tests/db/test_web_notice_actions.py`
- Depends on: U-web-settings-19
- Parallel: no
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given web changes 3, 4, 5 announced in three notices, When Undo of notice 5 is tapped, Then the values from before change 3 are restored with one audit record (AC-13, W-11) (type: happy; level: agent).
  2. Given the same burst, When Undo of notice 3 is tapped, Then the same result (AC-13) (type: edge; level: agent).
  3. Given Telegram changed the row after the burst, When Undo is tapped, Then nothing changes and the bot says it changed in the meantime (AC-13) (type: edge; level: agent).
  4. Given "Undo and lock", When tapped, Then `web_lock` is set even when the undo itself conflicts (AC-27, W-11) (type: security; level: db).
  5. Given "Undo and lock" tapped twice, When handled, Then one lock row and one undo (idempotent) (type: edge; level: db).
  6. Given the unlock command from the allowed user, When sent, Then `web_lock` is cleared; from anyone else nothing happens (AC-27) (type: security; level: agent).
  7. Given an expired token or a token used twice, When tapped, Then the message is edited to "Expired" or "Already done" and nothing is written (type: edge; level: agent).
  8. Given a tap from another chat or user with a valid token, When handled, Then ignored (type: security; level: agent).
  9. Given the real agent role, When the lock write runs, Then it works with the grants of U-07 and no other `web_auth` table is touched (ADR-0033) (type: security; level: db).
  10. Given a failure path, When logs are captured, Then no zone value or token appears (type: security; level: agent).

### U-web-settings-21: Web app shell, API client and session (R1)

- Layer: web
- Contract: React Router routes `/`, `/login`, `/settings` (anything else is a not-found page); TanStack Query client; the typed client generated from `docs/api/openapi.json` (`pnpm --filter web gen:api`, checked in CI); `useSession()` calls `GET /api/session` and keeps the CSRF token in memory only; `apiFetch` adds `X-CSRF-Token` to writes only; a 401 on a write sends the browser to `/login?notice=expired` (AC-12, first half); a 403 shows the full-page "This account is not allowed for this app." with "Back to sign in" and no settings data in the DOM; page titles per screen, `lang="en"`.
- Files: `apps/web/src/main.tsx`, `apps/web/src/App.tsx`, `apps/web/src/api/client.ts`, `apps/web/src/api/schema.d.ts` (generated), `apps/web/src/session/useSession.ts`, `apps/web/src/pages/AccessRefused.tsx`, `apps/web/index.html`
- Depends on: U-web-settings-02, U-web-settings-17
- Parallel: no
- Guardrails: guardrail-react, guardrail-react-router, guardrail-tanstack-query, guardrail-vite, guardrail-typescript, guardrail-vitest-rtl
- Criteria:
  1. Given `GET /api/session` answers 401, When `/settings` is opened, Then the app shows `/login` (AC-2) (type: security; level: component).
  2. Given a valid session, When `/login` is opened, Then the app shows `/settings` (type: happy; level: component).
  3. Given a session, When the app runs, Then the CSRF token is in memory only: not in `localStorage`, `sessionStorage`, cookies or any URL (AC-8, W-4) (type: security; level: component).
  4. Given a `PUT` and a `GET`, When sent, Then only the write carries `X-CSRF-Token` and no request carries credentials to another origin (type: happy; level: component).
  5. Given a 401 on a write, When received, Then nothing is retried and the app goes to `/login?notice=expired` (AC-12 first half) (type: happy; level: component).
  6. Given a 403, When received, Then the full-page refusal text and "Back to sign in", and no value of the settings in the DOM (AC-2, AC-24) (type: security; level: component).
  7. Given "Sign out", When pressed, Then `POST /auth/logout` with the token, then `/login` (AC-7) (type: happy; level: component).
  8. Given `openapi.json` changes, When `gen:api` runs in check mode, Then it fails if `schema.d.ts` is stale (AC-15) (type: error; level: ci).
  9. Given the built `index.html`, When read, Then it references no URL outside the same origin (fonts: Decisions needed D-2) and sets `lang="en"` (AC-14, AC-23) (type: security; level: ci).
  10. Given an unknown path, When opened, Then the not-found page with a link to `/settings`, a title, and no data (type: edge; level: component).

### U-web-settings-22: UI primitives: Button, Field, Banner, TimeField, Layout (R1)

- Layer: web
- Contract: presentation components from the screens document, tokens only: `Button` (primary, secondary, ghost, danger; `loading`, `disabled`), `Field` (label, hint, error, ids by `useId`), `Banner` (danger, success, info; title, text, optional action), `TimeField` (native `input type=time` step 60, the 24-hour text beside it, stepped 15-minute select fallback), `Layout` (skip link, header with Sign out, `main`, focus ring).
- Files: `apps/web/src/components/Button.tsx`, `apps/web/src/components/Field.tsx`, `apps/web/src/components/Banner.tsx`, `apps/web/src/components/TimeField.tsx`, `apps/web/src/components/Layout.tsx`
- Depends on: U-web-settings-02
- Parallel: yes (with the backend units)
- Guardrails: guardrail-react, guardrail-tailwind, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given each Button variant, When rendered, Then it uses the token classes and the 44 px minimum target class (pixel size is checked in U-28) (AC-23) (type: a11y; level: component).
  2. Given `loading`, When rendered, Then the label changes ("Saving..."), `aria-disabled` is set and a second click does nothing (AC-23, W-12) (type: edge; level: component).
  3. Given a Field with hint and error, When rendered, Then the label is linked, hint and error are in `aria-describedby`, `aria-invalid` is set only when invalid, the error has `role="alert"` and a visible "!" mark besides colour (AC-23) (type: a11y; level: component).
  4. Given the TimeField with a stored `22:10`, When rendered, Then the value is shown unchanged with "= 22:10"; the select fallback offers 15-minute values plus the unrounded stored value (C-7) (type: edge; level: component).
  5. Given Banner kinds, When rendered, Then danger and conflict use `role="alert"`, success and info use `role="status"`, and each has a border-left and bold title (AC-23) (type: a11y; level: component).
  6. Given a Banner re-rendered with the same props, When announced, Then it is not re-announced (one live region node kept) (AC-23) (type: edge; level: component).
  7. Given Layout, When tabbed, Then the skip link is first and moves focus to `main`; `:focus-visible` shows the token ring (AC-23) (type: a11y; level: component).
  8. Given every component in every state, When axe runs (contrast off in jsdom), Then no violation (AC-22) (type: a11y; level: component).
  9. Given `prefers-reduced-motion`, When set, Then no transition or animation runs (AC-23) (type: a11y; level: component).

### U-web-settings-23: Login page (R1)

- Layer: web
- Contract: `/login` (public): brand, `h1` "Sign in", the account to use ("Use the Google account `<email>`. It is the only account that can open this app."), one provider button (label from configuration), the fine print "This page only asks who you are (your name and e-mail). It never asks for access to your mail or calendar." The button starts a top-level navigation to `/auth/login?return_to=/settings`. Banner states: redirecting, session expired (`notice=expired`), and the refusal states of D-5. Where the account and button label come from: Decisions needed D-4.
- Files: `apps/web/src/pages/LoginPage.tsx`, `apps/web/src/pages/loginConfig.ts`, `apps/web/src/pages/LoginPage.test.tsx`
- Depends on: U-web-settings-21, U-web-settings-22
- Parallel: yes (with U-24)
- Guardrails: guardrail-react, guardrail-react-router, guardrail-a11y, guardrail-tailwind, guardrail-vitest-rtl
- Criteria:
  1. Given `/login`, When rendered, Then `h1` is first in `main`, the account is named and the no-mail-access sentence is shown (AC-24) (type: happy; level: component).
  2. Given the button is pressed, When handled, Then it is disabled, reads "Opening Google...", has `aria-busy`, a polite status is announced, and the browser navigates to `/auth/login?return_to=/settings` (AC-6, AC-23) (type: happy; level: component).
  3. Given `?notice=expired`, When rendered, Then an info banner with `role="status"`: "Your session ended. Sign in again." (R1 text without "what you typed is kept") (AC-12 first half) (type: happy; level: component).
  4. Given the refusal state of D-5, When rendered, Then a banner with `role="alert"`: "This account is not allowed for this app. Try the account named above." and no provider detail, rendered with the page so it is announced (AC-24) (type: error; level: component).
  5. Given `?notice=<script>` or any unknown value, When rendered, Then no banner and nothing from the URL appears in the DOM (AC-14, W-5) (type: security; level: component).
  6. Given a `return_to` in the page URL, When the button is pressed, Then the navigation still uses `/settings` (AC-6, W-2) (type: security; level: component).
  7. Given axe, When run on each state, Then no violation; keyboard Tab reaches the button first (AC-23) (type: a11y; level: component).

### U-web-settings-24: Settings form: load, validate, save (R1)

- Layer: web
- Contract: `/settings` with `useSettings()` (query `['settings']`) and a save mutation (`PUT` with `{values, version}`), the fields in the order Time zone (a plain text field until U-25 replaces it with the combobox), Quiet hours (From, Until), Daily overview, Remind-me-later default, each with a one-line hint; states loading, loaded, dirty, saving, validation error (422), save failed. Words match Telegram (C-11).
- Files: `apps/web/src/features/settings/SettingsPage.tsx`, `apps/web/src/features/settings/SettingsForm.tsx`, `apps/web/src/features/settings/useSettings.ts`, `apps/web/src/features/settings/fieldErrors.ts`, `apps/web/src/features/settings/SettingsPage.test.tsx`
- Depends on: U-web-settings-01, U-web-settings-21, U-web-settings-22
- Parallel: yes (with U-23)
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-tailwind, guardrail-vitest-rtl
- Criteria:
  1. Given the loading state, When rendered, Then skeleton rows, the text "Loading your settings", `aria-busy`, and no Save button yet (AC-22) (type: happy; level: component).
  2. Given loaded settings, When rendered, Then the four fields in order, labelled "Time zone", "Quiet hours" (From, Until), "Daily overview", "Remind-me-later default", each with a hint linked by `aria-describedby` (AC-1, C-11) (type: happy; level: component).
  3. Given nothing changed, When viewed, Then Save is disabled; after an edit it is enabled (type: happy; level: component).
  4. Given Save is pressed, When the request runs, Then the label is "Saving...", Save is `aria-disabled`, inputs are read-only, a polite status says "Saving your settings." and exactly one `PUT` with `{values, version}` and the token is sent even on a double click (AC-9, AC-23, W-12) (type: edge; level: component).
  5. Given a 422 with problems for two fields, When shown, Then each message is next to its field with "!" and a red border, `aria-invalid`, `aria-describedby` hint plus error, `role="alert"`, and focus moves to the first invalid field in DOM order (AC-10, AC-23) (type: error; level: component).
  6. Given a network error or 5xx, When shown, Then a danger banner "Could not save. Nothing was changed." with "Try again", typed values kept (type: error; level: component).
  7. Given the API returns a value like `<img src=x onerror=alert(1)>` for the zone, When rendered, Then it appears as text and no element is created (AC-14, W-5) (type: security; level: component).
  8. Given keyboard only, When the user tabs through, edits, submits invalid, fixes and saves, Then the whole flow works and focus is visible (AC-23) (type: a11y; level: component).
  9. Given axe on loading, loaded, dirty, saving, validation error and save-failed states, When run, Then no violation (AC-22) (type: a11y; level: component).

### U-web-settings-25: ZoneCombobox with live time (R1)

- Layer: web
- Contract: ARIA 1.2 combobox with list autocomplete for the time zone: `GET /api/places?q=` (debounced), options "Bangkok, Thailand, UTC+7, 03:42 now", the stored value shown as "Currently: Europe/Amsterdam", and a live local-time paragraph computed in the browser with `Intl.DateTimeFormat` from an injected clock; keyboard model and announcements from the screens document.
- Files: `apps/web/src/features/settings/ZoneCombobox.tsx`, `apps/web/src/features/settings/useZoneSearch.ts`, `apps/web/src/features/settings/liveTime.ts`, `apps/web/src/features/settings/ZoneCombobox.test.tsx`
- Depends on: U-web-settings-18, U-web-settings-24
- Parallel: no
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the combobox, When rendered, Then `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete="list"` and `aria-activedescendant` are set correctly through open and close (AC-23, C-7) (type: a11y; level: component).
  2. Given the user types "bang", When the search resolves, Then options read "Bangkok, Thailand, UTC+7, 03:42 now" and a hidden polite region says "3 places found" (C-7) (type: happy; level: component).
  3. Given the keyboard, When Down, Up, Enter, Escape, a second Escape, Tab, Home and End are used, Then the active option moves with focus staying in the input, Enter selects, Escape closes, the second Escape restores the saved value, Tab accepts nothing unselected (AC-23) (type: a11y; level: component).
  4. Given a chosen zone and a fake clock, When the paragraph updates, Then "In Amsterdam it is 21:42 right now." appears after a 300 ms pause and on selection, inside an `aria-live="polite"` region, correct on both sides of a clock change (C-7, AC-28) (type: happy; level: component).
  5. Given text with no match, When the search returns empty, Then the hint "Nothing found for 'Phuket'. Try the nearest bigger city, or the country." (not red, not `role="alert"`), and a suggestion from the API is offered (C-7) (type: error; level: component).
  6. Given the field loses focus with unselected text, When blurred, Then the saved value returns; it is never left empty (type: edge; level: component).
  7. Given a place label with markup from the API, When shown, Then it is text only (AC-14) (type: security; level: component).
  8. Given two searches where the first answers late, When both resolve, Then only the latest result is shown (type: edge; level: component).
  9. Given the typed query, When the page is inspected, Then it is in no URL, storage or log (W-13) (type: security; level: component).
  10. Given axe on closed, open, empty and no-result states, When run, Then no violation (AC-22) (type: a11y; level: component).

### U-web-settings-26: Save feedback: last-change line, saved banner, zone preview (R1)

- Layer: web
- Contract: `LastChangeLine` ("Last changed from Telegram at 14:02" with `<time datetime>`, from the web, or "Using the default settings." at version 0); the saved banner with what is true now and the notice interval N (the source of N: Decisions needed D-1); the permanent sentence under the times and the zone hint; the zone-change preview computed from the form values with the injected clock; the zone is the first field.
- Files: `apps/web/src/features/settings/LastChangeLine.tsx`, `apps/web/src/features/settings/SavedBanner.tsx`, `apps/web/src/features/settings/ZonePreview.tsx`, `apps/web/src/features/settings/zoneMath.ts`, `apps/web/src/features/settings/SaveFeedback.test.tsx`
- Depends on: U-web-settings-24, U-web-settings-25
- Parallel: yes (with U-27)
- Guardrails: guardrail-react, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the last change from Telegram at 14:02 Amsterdam time, When shown, Then the line reads "Last changed from Telegram at 14:02" with `<time datetime>`; from the web it says "from the web"; at version 0 "Using the default settings." (AC-1, C-6) (type: happy; level: component).
  2. Given a successful save at 21:42 in Bangkok, When the banner shows, Then "Saved at 21:42. Quiet hours are 23:00 to 07:00 (Bangkok time). A message with an Undo button follows on Telegram within about N minutes." with `role="status"`, focus staying on Save, and the line now says "from the web" (AC-28, AC-13) (type: happy; level: component).
  3. Given N of 1 and of 5 minutes, When rendered, Then "about 1 minute" and "about 5 minutes" (type: edge; level: unit).
  4. Given the zone is changed from Europe/Amsterdam to Asia/Bangkok before saving, When previewed, Then "Quiet hours will now be 22:00 to 07:00 Bangkok time (16:00 to 01:00 Amsterdam time)." and the form's clock times are unchanged (AC-28) (type: happy; level: component).
  5. Given the zone is changed back to the saved one, When previewed, Then the preview disappears (type: edge; level: component).
  6. Given zones with half-hour offsets (Asia/Kolkata), a day boundary and a date inside a clock change, When previewed, Then the converted times are correct for the injected date (AC-28) (type: edge; level: unit).
  7. Given the page, When rendered, Then Time zone is the first field in DOM and tab order, the permanent sentence "Quiet hours, the overview and reminders follow this time zone." and the zone hint "The times below are local times in this zone." are present (AC-28) (type: happy; level: component).
  8. Given the preview and the banner, When read by a screen reader, Then neither is `role="alert"` and the success banner is the only live announcement of the save (AC-23) (type: a11y; level: component).

### U-web-settings-27: Conflict handling: Use mine and Keep Telegram's (R1)

- Layer: web
- Contract: on 409 the form takes the returned `Settings`, shows the info banner (`role="alert"`, focus moves to it) and marks every field Marco had edited with his own value and two buttons "Use mine" and "Keep Telegram's"; nothing is saved until Save is pressed again with the new version.
- Files: `apps/web/src/features/settings/ConflictBanner.tsx`, `apps/web/src/features/settings/useConflict.ts`, `apps/web/src/features/settings/SettingsForm.tsx`, `apps/web/src/features/settings/Conflict.test.tsx`
- Depends on: U-web-settings-24
- Parallel: yes (with U-25, U-26)
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the page at version 1 and a 409 with version 2, When shown, Then the banner "Settings changed in Telegram at 14:02 (Amsterdam time). I loaded the new values." has `role="alert"` and focus, and the fields show the new values (AC-11) (type: happy; level: component).
  2. Given Marco edited quiet start to 22:30 and Telegram has 23:00, When shown, Then that field says "You typed 22:30, Telegram now has 23:00" with "Use mine" and "Keep Telegram's"; fields he did not edit have no mark (AC-28) (type: happy; level: component).
  3. Given "Use mine", When pressed, Then the field holds 22:30 again as an unsaved edit (AC-28) (type: happy; level: component).
  4. Given "Keep Telegram's", When pressed, Then the mark is gone and the field holds 23:00 (AC-28) (type: happy; level: component).
  5. Given the conflict, When no button and no Save is pressed, Then nothing is sent; Save afterwards sends the new version (AC-11) (type: edge; level: component).
  6. Given the other change came from the web in another tab, When shown, Then the banner says "from the web" (type: edge; level: component).
  7. Given a second 409 while resolving, When it arrives, Then the banner and marks are recomputed against the newest values (type: edge; level: component).
  8. Given the buttons, When read by a screen reader, Then each is named with its field ("Use mine for Quiet hours") and axe finds no violation (AC-23) (type: a11y; level: component).

### U-web-settings-28: Accessibility and responsive states: Playwright ui-states (R1)

- Layer: web
- Contract: a Playwright project `ui-states` with a stubbed API (`route.fulfill`, no backend) that renders every state of the login page (default, redirecting, expired, refused) and the settings page (loading, loaded, dirty, saving, saved, validation error, save failed, conflict, 403, session expired) at 320, 375, 768 and 1280 px, in light and dark, and at 200 % text size. This is the pixel-level check of AC-22 and AC-23.
- Files: `apps/web/e2e/ui-states.spec.ts`, `apps/web/e2e/support/stubs.ts`, `apps/web/playwright.config.ts`
- Depends on: U-web-settings-23, U-web-settings-24, U-web-settings-25, U-web-settings-26, U-web-settings-27
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y
- Criteria:
  1. Given every state at every viewport, When measured, Then `scrollWidth` is at most `clientWidth` (no horizontal scroll) (AC-22) (type: a11y; level: playwright).
  2. Given every state at every viewport in light and dark, When axe runs with contrast on, Then no violation (AC-22) (type: a11y; level: playwright).
  3. Given text at 200 % size, When rendered, Then nothing is clipped or overlaps, and Save and the secondary button stack with Save first at 320 px (AC-22) (type: edge; level: playwright).
  4. Given the keyboard only, When the login to saved flow runs on stubs, Then every step is reachable, and on submit with an invalid field focus lands on the first invalid field (AC-23) (type: a11y; level: playwright).
  5. Given each interactive element, When focused, Then the outline is visible with a computed non-zero width and the token colour (AC-23) (type: a11y; level: playwright).
  6. Given every target, When measured, Then at least 24 px on any viewport and at least 44 px on the touch viewports, with 8 px between neighbours (AC-23) (type: a11y; level: playwright).
  7. Given a slow stubbed save, When pending, Then Save is disabled and a second click sends no second request (AC-23, W-12) (type: edge; level: playwright).
  8. Given `prefers-reduced-motion: reduce`, When rendered, Then computed animation and transition durations are 0 (AC-23) (type: a11y; level: playwright).
  9. Given the `ui-states` project, When run in CI, Then it needs no backend and runs in the `web` job (type: happy; level: ci).

### U-web-settings-29: Exposed routes: nginx exact routes and ingress with TLS (R1)

- Layer: infra
- Contract: `apps/web/nginx.conf` serves exactly `/`, `/login`, `/settings` (the single page), `/assets/*` and answers 404 for everything else (including `/docs`, `/redoc`, `/openapi.json`, `/healthz`, `/readyz`, `/metrics`); it keeps the CSP for HTML and adds HSTS (`max-age=31536000; includeSubDomains`, no preload). The `app` chart ingress routes `/api` and `/auth` to `api` and `/` to `web`, redirects HTTP to HTTPS, requires TLS 1.2 or higher, has a cert-manager issuer annotation per environment, and uses `ingress.hsts` (today no template reads it). Controller-specific parts (body cap of 8 KB, TLS minimum, log format with `$uri`) come from per-environment values (open point: hosting).
- Files: `apps/web/nginx.conf`, `apps/web/tests/nginx-routes.test.mjs`, `deploy/charts/app/templates/ingress.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/envs/local/values.yaml`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-docker, guardrail-kubernetes, guardrail-helm, guardrail-tls-certificates
- Criteria:
  1. Given the built web image, When `/`, `/login`, `/settings` are requested, Then 200 with the index page, the CSP and `nosniff`; `/assets/<hash>.js` is served immutable (type: happy; level: image).
  2. Given `/docs`, `/redoc`, `/openapi.json`, `/healthz`, `/readyz`, `/metrics`, `/api/docs`, `/auth/login` and `/anything`, When requested from the web image, Then 404 each (AC-19, W-6) (type: security; level: image).
  3. Given the default image configuration, When read, Then it has no `proxy_pass` (the compose-only proxy lives in a file the prod-like profile mounts, if still needed) (type: security; level: image).
  4. Given an HTML response, When inspected, Then `Strict-Transport-Security: max-age=31536000; includeSubDomains` is present and `preload` is absent (AC-18, W-9) (type: security; level: image).
  5. Given the rendered ingress, When read, Then paths are exactly `/api` and `/auth` to the api service and `/` to web, and no rule routes `/docs`, `/openapi.json`, `/healthz`, `/readyz` or `/metrics` to the api (AC-19) (type: security; level: chart).
  6. Given the rendered ingress with `tls.enabled`, When read, Then a `tls` block with the host and secret, an HTTP to HTTPS redirect, the cert-manager issuer annotation and the HSTS setting from `ingress.hsts` (AC-18, W-9) (type: security; level: chart).
  7. Given the values schema, When a production values file sets `tls.enabled: false` or `hsts: false`, Then `helm lint --strict` fails (AC-18) (type: error; level: chart).
  8. Given the local environment values (kind, Traefik), When rendered, Then the 8 KB body cap, TLS 1.2 minimum and a log format without the query string are set through values; the chart default has no controller-specific annotation (AC-16, W-9, W-13) (type: security; level: chart).
  9. Given the rendered output, When checked with kubeconform and kube-linter, Then both pass (type: happy; level: chart).

### U-web-settings-30: Chart: NetworkPolicy, one replica, secrets, migrate Secret (R1)

- Layer: infra
- Contract: ADR-0034, ADR-0029, design section "Deployment". The `app` chart: `api.replicas` is 1 (schema maximum 1); `api` and `web` ingress NetworkPolicy accepts from one peer (namespace selector and pod selector in one `from` item) selecting the ingress controller; `api` egress to the database, DNS and TCP 443 outside private ranges; no `web-to-api` rule; the api reads client secret, database URL of the web role, subject-hash key and CSRF key from the Secret `<release>-api` (SealedSecret; created by the operator, README step), plain values for issuer, client id, allowed `sub` and public origin; the `worker` chart's migration Secret gains `WEB_ROLE_PASSWORD`. An optional certificate expiry alert at least 14 days ahead: Decisions needed D-7.
- Files: `deploy/charts/app/templates/networkpolicy.yaml`, `deploy/charts/app/templates/workloads.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/charts/worker/templates/migration.yaml`, `deploy/charts/worker/README.md`
- Depends on: U-web-settings-07, U-web-settings-29
- Parallel: no
- Guardrails: guardrail-kubernetes, guardrail-helm, guardrail-tls-certificates
- Criteria:
  1. Given the rendered api Deployment, When read, Then `replicas: 1`; a values file with 2 fails the schema (ADR-0034, W-7) (type: security; level: chart).
  2. Given the rendered NetworkPolicy, When read, Then ingress to `api` and `web` has exactly one `from` item with a namespace selector and a pod selector together, and no empty selector (W-9) (type: security; level: chart).
  3. Given the render, When searched, Then there is no `web-to-api` rule and no policy that admits every namespace (design, W-9) (type: security; level: chart).
  4. Given the api egress, When read, Then only database, DNS (UDP and TCP 53) and TCP 443 to addresses outside 10/8, 172.16/12, 192.168/16 and 169.254/16; the accepted risk and review date 2027-05-10 are in the chart README (W-9) (type: security; level: chart).
  5. Given the api container env, When read, Then client secret, database URL, subject-hash key and CSRF key come from `secretKeyRef` of `<release>-api` and appear in no values file, ConfigMap or template literal (ADR-0029, W-1) (type: security; level: chart).
  6. Given the chart and the README, When searched for `sslmode=disable`, `verify-none`, `insecure`, `SSL_CERT_FILE`, Then no hit; the README documents `sslmode=verify-full` for the database URL (W-8, W-9) (type: security; level: chart).
  7. Given the migrate Job, When rendered, Then it reads `WEB_ROLE_PASSWORD` from the migration Secret; a missing key makes the job fail naming the key (type: error; level: chart).
  8. Given the README, When checked, Then sealing uses standard input and no `--from-literal=` for secret keys, and the new keys are listed (ADR-0029) (type: security; level: chart).
  9. Given `helm lint --strict`, kubeconform and kube-linter for the `app` and `worker` charts, When run, Then they pass (readiness `/readyz`, liveness `/healthz`, non-root, read-only root file system) (type: happy; level: chart).

### U-web-settings-31: Prod-like profile: Caddy edge, mock provider, TLS database, migrate (R1)

- Layer: infra
- Contract: the `prod-like` compose profile gains a Caddy edge (TLS from an internal CA, HTTP to HTTPS redirect, HSTS, `/api` and `/auth` to `api`, the rest to `web`, a log format without the query string), the `mock-oidc` container (U-10) served over HTTPS through the edge under a fixed host name with a network alias for `api` and `web`, the api trusting the internal CA through `SSL_CERT_FILE` (compose only), PostgreSQL serving TLS with a certificate from the same CA so the web role's URL can use `sslmode=verify-full`, the migrate service creating both roles, and e2e-only configuration (raised sign-in limits). No secret in `compose.yaml`; every value comes from the environment.
- Files: `compose.yaml`, `agents/mail-triage/compose.yaml`, `deploy/prod-like/Caddyfile`, `tools/mock-oidc/Dockerfile`, `deploy/prod-like/certs.sh`
- Depends on: U-web-settings-03, U-web-settings-07, U-web-settings-10
- Parallel: yes (with U-17 to U-28)
- Guardrails: guardrail-compose, guardrail-docker, guardrail-tls-certificates
- Criteria:
  1. Given `docker compose --profile prod-like up -d --wait` after the migrate service has run, When finished, Then db, api, web, edge and mock-oidc are healthy (type: happy; level: image).
  2. Given plain HTTP to the edge, When requested, Then a redirect to HTTPS; an HTTPS response carries `Strict-Transport-Security` (AC-18, W-9) (type: security; level: image).
  3. Given the api container, When it signs in against the mock provider, Then the call goes over HTTPS through the edge with the CA from `SSL_CERT_FILE`; the Helm values contain no CA or verify setting (W-2, W-9) (type: security; level: image).
  4. Given the web role's database URL, When the api connects, Then `sslmode=verify-full` succeeds against the TLS database and fails with a wrong host name (W-8, W-9) (type: security; level: image).
  5. Given `docker compose run --rm mail-triage-migrate`, When it runs against a fresh database, Then both runtime roles exist and the owner is not used by any runtime container (AC-17) (type: security; level: image).
  6. Given `docker compose --profile prod-like config`, When searched, Then no literal secret, and every sensitive value is an environment reference (guardrail-compose) (type: security; level: ci).
  7. Given the hardening anchor, When the new services are read, Then `read_only`, `no-new-privileges` and `cap_drop: ALL` apply, and ports bind to `127.0.0.1` only (type: security; level: ci).
  8. Given the default and the `dev` profiles, When rendered, Then the raised e2e limits are not set there (AC-16) (type: security; level: ci).
  9. Given the edge log, When a request with a query string is made, Then the logged line has the path only (AC-20, W-13) (type: security; level: image).
  10. Given the mock provider, When called with `login_hint` for the allowed user and for the second user, Then each completes without interaction (type: happy; level: image).

### U-web-settings-32: Journey and the single prod-like CI job (R1)

- Layer: infra
- Contract: one CI job `prod-like` replaces the separate `e2e` and `runtime-role` jobs, in this order: start the database; run the migrate service; `up --wait`; database and role checks (the 19 forbidden statements of the agent role from U-quiet-hours-15b plus the web role's); Playwright `setup` project (signs in once through the mock provider and saves the storage state), then `journey` (one worker; the settings row is reset by owner SQL between tests); then a log-grep check. The `ui-states` project of U-28 stays in the `web` job. The agent is not in the prod-like stack (it needs real Gmail, Telegram and Anthropic credentials), so notices are covered at agent level (U-19, U-20).
- Files: `apps/web/e2e/setup.ts`, `apps/web/e2e/journey.spec.ts`, `apps/web/playwright.config.ts`, `.github/workflows/ci.yml`, `agents/mail-triage/tests/e2e/test_web_role.py`
- Depends on: U-web-settings-13, U-web-settings-14, U-web-settings-17, U-web-settings-28, U-web-settings-30, U-web-settings-31
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y, guardrail-docker, guardrail-compose
- Criteria:
  1. Given `ci.yml`, When read, Then one job runs the stated sequence and the old `e2e` and `runtime-role` jobs are gone with their checks kept (type: happy; level: ci).
  2. Given the `setup` project, When it runs, Then the allowed user is signed in through the mock provider and the storage state is reused by the journey (AC-2, AC-7) (type: happy; level: playwright).
  3. Given a signed-in context, When `/settings` opens, Then the seeded values and the last-change line show; a save of a valid change shows the saved banner and a reload shows the stored values (AC-1, AC-9) (type: happy; level: playwright).
  4. Given two browser contexts on version 1, When context B saves and context A saves afterwards, Then A gets the conflict banner with the new values and "Use mine" / "Keep Telegram's" (AC-11, AC-28) (type: edge; level: playwright).
  5. Given the session row is aged by owner SQL, When Save is pressed, Then nothing is stored, the browser goes to `/login`, and after signing in `/settings` shows the stored values (AC-12 first half) (type: edge; level: playwright).
  6. Given the second mock user, When signing in, Then the "This account is not allowed for this app" page and no `__Host-session` cookie (AC-3, AC-24) (type: security; level: playwright).
  7. Given an injected inline script and a request for an external script, When the page loads, Then a `securitypolicyviolation` event fires and the script does not run; the CSP header matches (AC-14, W-5) (type: security; level: playwright).
  8. Given `/docs`, `/redoc`, `/openapi.json`, `/healthz`, `/readyz`, `/metrics` through the edge, and plain HTTP, When requested, Then 404 for the first six and a redirect to HTTPS with HSTS for the last (AC-18, AC-19) (type: security; level: playwright).
  9. Given a sign-in has happened, When the logs of `api`, `web` and the edge are grepped, Then neither the authorization code, the state, `code=` nor the session cookie value appears (AC-20 first half, W-13) (type: security; level: ci).
  10. Given the web role in the running stack, When it reads `mail_item`, `oauth_token` or `settings_change`, runs DDL, or writes a bad `updated_by`, Then SQLSTATE 42501 each (AC-17, W-8) (type: security; level: ci).

### U-web-settings-33: Mutation scope for the pure security modules (R1)

- Layer: infra
- Contract: ADR-0030 item 4 extended to the backend: `backend/cosmic-ray.toml` lists the pure security modules (`app/auth/identity.py`, `app/auth/token.py`, `app/auth/expiry.py`, `app/auth/csrf.py`, `app/auth/return_to.py`, `app/limits.py`, `app/clientaddr.py`, `app/settings_fields.py`, the `subject_digest` function in `app/security_events.py`); `.github/workflows/mutation.yml` gets a `backend` job like the others (schedule and manual start, fails below 85 %).
- Files: `backend/cosmic-ray.toml`, `.github/workflows/mutation.yml`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/tests/test_mutation_scope.py`
- Depends on: U-web-settings-10, U-web-settings-11, U-web-settings-12, U-web-settings-14, U-web-settings-15, U-web-settings-17
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given `mutation.yml`, When read, Then a `backend` job triggers on `schedule` and `workflow_dispatch`, runs cosmic-ray and fails when more than 15 % of mutants survive (ADR-0030) (type: happy; level: ci).
  2. Given `cosmic-ray.toml`, When read, Then the module list equals the named pure modules, no more and no less (type: happy; level: unit).
  3. Given each named module, When its imports are read, Then none imports FastAPI, SQLAlchemy or the network, so the mutation run needs no database (type: edge; level: unit).
  4. Given boundary rows, When listed, Then tests exist for idle 29:59 and 30:00, absolute 11:59:59 and 12:00:00, the 30th and 31st request, 8192 and 8193 bytes, 31 and 32 key bytes, `azp` present and absent, and window 59.9 and 60.0 s (kills `<` vs `<=`, off-by-one) (type: security; level: unit).
  5. Given the first manual run, When it finishes, Then its score and the surviving mutants are recorded under "Changes made during the build" and each survivor is killed or explained (type: happy; level: review).

### U-web-settings-34: Reset to defaults: backend (R2)

- Layer: backend
- Contract: `POST /api/settings/reset` (session, CSRF, Origin) with `{version}` writes `DEFAULT_POLICY` through the same repository and validation as `PUT`; 200 `Settings`, 409 on an old version. The allow-list gains the path.
- Files: `backend/app/routers/settings.py`, `backend/tests/test_settings_reset_api.py`, `backend/tests/test_route_inventory.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-17
- Parallel: yes (with U-36, U-37, U-38)
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given a changed row, When reset at the current version, Then the defaults including the time zone are stored through the repository and 200 with the new `Settings` (AC-25) (type: happy; level: db).
  2. Given the reset, When the audit is read, Then one record with channel web and `updated_by` of the form `web:<32 hex>` exists (AC-25, W-10) (type: security; level: db).
  3. Given an old version, When reset, Then 409 with the current `Settings` and nothing changes (AC-11) (type: edge; level: api).
  4. Given no token, a wrong `Origin` or no session, When reset, Then 403 or 401 and nothing changes (AC-8, AC-25) (type: security; level: api).
  5. Given a GET on the route, When sent, Then 405 (AC-8) (type: security; level: api).
  6. Given the reset, When the agent next runs, Then a web notice follows like any web change (AC-13) (type: happy; level: agent).
  7. Given the rate bucket, When exceeded, Then 429 (AC-16) (type: security; level: api).
  8. Given the route inventory, When read, Then the path is on the allow-list and has the session and csrf markers (AC-15) (type: security; level: unit).

### U-web-settings-35: Reset to defaults: web (R2)

- Layer: web
- Contract: the secondary button "Reset to defaults", kept apart from Save, opens `ConfirmDialog` (`role="alertdialog"` or native `<dialog>` with `showModal`) that names the values including the time zone; the destructive button reads "Replace my settings with defaults", initial focus is "Keep my settings"; on confirm the page calls `POST /api/settings/reset`, shows the saving state and the banner "Defaults restored. The Undo button is in the Telegram message."
- Files: `apps/web/src/components/ConfirmDialog.tsx`, `apps/web/src/features/settings/ResetButton.tsx`, `apps/web/src/features/settings/SettingsForm.tsx`, `apps/web/src/features/settings/Reset.test.tsx`, `apps/web/e2e/ui-states.spec.ts`
- Depends on: U-web-settings-24, U-web-settings-34
- Parallel: no
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl, guardrail-playwright
- Criteria:
  1. Given the dialog opens, When rendered, Then it lists "Time zone Europe/Amsterdam, quiet hours 23:00 to 07:00, daily overview 18:00, reminders 09:00", says the time zone is reset too, and initial focus is "Keep my settings" (AC-25) (type: a11y; level: component).
  2. Given the dialog, When Escape or "Keep my settings" is used, Then it closes, nothing is sent and focus returns to the Reset button (AC-25) (type: happy; level: component).
  3. Given the dialog open, When Tab is pressed repeatedly, Then focus stays inside and the page behind is inert (AC-23) (type: a11y; level: component).
  4. Given confirm, When pressed, Then Save and Reset are disabled, one `POST /api/settings/reset` with the version is sent, and the banner "Defaults restored. The Undo button is in the Telegram message." shows (AC-25) (type: happy; level: component).
  5. Given a 409 on reset, When received, Then the conflict banner of U-27 shows and nothing is replaced (AC-11) (type: edge; level: component).
  6. Given the two dialog buttons, When viewed in greyscale, Then the destructive one differs by label, border and weight, not by colour alone (ADR-0035) (type: a11y; level: playwright).
  7. Given the dialog at 320, 375, 768 and 1280 px and 200 % text, When rendered, Then no horizontal scroll and axe finds no violation (AC-22) (type: a11y; level: playwright).
  8. Given the secondary button at 320 px and at 200 % text, When rendered, Then it is stacked below Save and kept apart (AC-22) (type: edge; level: playwright).

### U-web-settings-36: Typed values kept across session expiry (R2)

- Layer: web
- Contract: when a save is answered with 401, the typed values are kept and restored after sign-in at `/settings`, with the banner "Welcome back. Your unsaved changes are restored. Check them and save."; they are never saved automatically. Where the draft lives across the provider round trip (a top-level navigation drops memory): Decisions needed D-6. The login banner then says "Your session ended. Sign in again; what you typed is kept."
- Files: `apps/web/src/features/settings/useDraft.ts`, `apps/web/src/features/settings/SettingsForm.tsx`, `apps/web/src/pages/LoginPage.tsx`, `apps/web/src/features/settings/Draft.test.tsx`
- Depends on: U-web-settings-23, U-web-settings-24
- Parallel: yes (with U-34, U-37, U-38)
- Guardrails: guardrail-react, guardrail-a11y, guardrail-vitest-rtl, guardrail-typescript
- Criteria:
  1. Given a 401 on save with edited fields, When the user signs in again and returns, Then the edited values are restored in the form, the banner shows, and no request was sent for them (AC-12 second half) (type: happy; level: component).
  2. Given the restored draft, When the page loads, Then Save is enabled and nothing is saved until the user presses it (AC-12) (type: edge; level: component).
  3. Given the draft store, When read, Then it holds only the five values and the version, never a token, e-mail or CSRF value (AC-8, W-4) (type: security; level: component).
  4. Given sign-out, a successful save or "Keep Telegram's" for every field, When completed, Then the draft is removed (type: edge; level: component).
  5. Given the stored version is older than the server's after sign-in, When restored, Then the conflict flow of U-27 shows with the draft as Marco's values (AC-11, AC-28) (type: edge; level: component).
  6. Given a draft older than 12 hours by the injected clock, When the page loads, Then it is discarded (type: edge; level: component).
  7. Given the login page with a draft present, When rendered, Then it adds "what you typed is kept"; without a draft it does not (type: edge; level: component).
  8. Given axe on the restore banner state, When run, Then no violation and the banner is `role="status"` (AC-23) (type: a11y; level: component).

### U-web-settings-37: Telegram alert after 5 refused sign-ins (R2)

- Layer: agent
- Contract: the agent role gains `SELECT` on `web_auth.security_event` (grants.sql); at each run it counts `signin_refused` events in the last 10 minutes; at 5 or more it sends one notice (count, issuer, time, no `sub`), at most one per 10 minutes. Protocol failures (`signin_failed`) never count and never alert.
- Files: `agents/mail-triage/app/usecases/signin_alert.py`, `agents/mail-triage/app/db/pg_signin_events.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/tests/db/test_signin_alert.py`
- Depends on: U-web-settings-09, U-web-settings-19
- Parallel: yes (with U-34, U-36, U-38)
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given 5 `signin_refused` events within 10 minutes (`FakeClock`), When the agent runs, Then one notice with the count, the issuer and the time and no `sub` (AC-20 second half, W-13) (type: happy; level: agent).
  2. Given 4 events, or 5 events spread over 11 minutes, When the agent runs, Then no notice (AC-20) (type: edge; level: agent).
  3. Given 50 `signin_failed` events (missing state and similar), When the agent runs, Then no notice (AC-20) (type: security; level: agent).
  4. Given a notice was sent, When the agent runs again within 10 minutes with more events, Then no second notice; after 10 minutes a new one may follow (type: edge; level: agent).
  5. Given the agent role, When it selects `security_event`, Then it works; when it inserts, updates or deletes there, or touches `session` or `login_flow`, Then 42501 (type: security; level: db).
  6. Given logs and the notice text, When captured, Then no hash, `sub` or token appears (W-13) (type: security; level: agent).

### U-web-settings-38: Audit retention purge in the migrate job (R2)

- Layer: backend (database; agent image)
- Contract: `python -m app purge` removes `settings.settings_change` records older than one year (decided by the injected clock) under the owner role as a step of the migrate job, after migrate and grants; not a CronJob and not a runtime role. The worker chart's Job and the compose migrate service run the step.
- Files: `agents/mail-triage/app/db/purge.py`, `agents/mail-triage/app/db/migrate.py`, `agents/mail-triage/app/__main__.py`, `deploy/charts/worker/templates/migration.yaml`, `agents/mail-triage/tests/db/test_purge.py`
- Depends on: U-web-settings-07, U-web-settings-30
- Parallel: yes (with U-34, U-36, U-37)
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-python, guardrail-helm, guardrail-kubernetes
- Criteria:
  1. Given records at 366 days and 364 days old (`FakeClock`), When the purge runs, Then only the older one is removed (AC-21) (type: happy; level: db).
  2. Given a record exactly 365 days old, When the purge runs, Then the boundary follows one rule, tested on both sides (AC-21) (type: edge; level: db).
  3. Given the runtime role and the web role, When they delete from `settings_change`, Then 42501 still (AC-17) (type: security; level: db).
  4. Given the migrate job, When it runs, Then the order is migrate, grants, purge, and a failing purge makes the job exit non-zero naming the step (AC-21) (type: error; level: db).
  5. Given the rendered worker chart, When searched, Then there is no `CronJob` and no workload with the owner secret other than the migrate Job (AC-21, W-13) (type: security; level: chart).
  6. Given the purge, When logs are captured, Then only the count of removed rows is logged (type: security; level: db).
  7. Given the purge run twice, When repeated, Then the second removes nothing (type: edge; level: db).

## Coverage of the acceptance criteria

Every criterion of the spec has at least one unit; the second halves are R2.

| AC | Unit |
| --- | --- |
| AC-1 | 17, 24, 26, 32 |
| AC-2 | 12, 17, 21, 32 |
| AC-3 | 10, 13, 32 |
| AC-4 | 04, 08 |
| AC-5 | 10, 13 |
| AC-6 | 11, 13, 23 |
| AC-7 | 12, 13, 14, 21, 32 |
| AC-8 | 14, 17, 21, 34 |
| AC-9 | 06, 16, 17, 24, 32 |
| AC-10 | 16, 17, 24 |
| AC-11 | 16, 17, 24, 27, 32 |
| AC-12 (first half, R1) | 12, 21, 23, 32 |
| AC-12 (second half, R2) | 36 |
| AC-13 | 19, 20, 26, 34 |
| AC-14 | 05, 17, 21, 24, 25, 32 |
| AC-15 | 05, 14, 17, 18, 21 |
| AC-16 | 11, 15, 18, 29 |
| AC-17 | 06, 07, 16, 31, 32, 38 |
| AC-18 | 29, 31, 32 |
| AC-19 | 05, 29, 32 |
| AC-20 (first half, R1) | 09, 13, 14, 15, 31, 32 |
| AC-20 (second half, R2) | 37 |
| AC-21 (R2) | 38 |
| AC-22 | 01, 02, 22, 24, 28 |
| AC-23 | 22, 24, 25, 28 |
| AC-24 | 13, 21, 23, 32 |
| AC-25 (R2) | 34, 35 |
| AC-26 | 16 |
| AC-27 | 12, 13, 20 |
| AC-28 | 01, 25, 26, 27, 32 |

Check: AC-1 to AC-28 all appear (AC-12, AC-20, AC-21 and AC-25 with their R2 halves). No acceptance criterion is left without a unit.

## Coverage of the threats

| Threat | Units |
| --- | --- |
| W-1 | 04, 10, 13, 17, 30 |
| W-2 | 10, 11, 13, 23, 31 |
| W-3 | 12, 14 |
| W-4 | 04, 14, 21, 36 |
| W-5 | 05, 17, 24, 32 |
| W-6 | 05, 13, 29 |
| W-7 | 11, 15, 30 |
| W-8 | 06, 07, 08, 16, 31, 32 |
| W-9 | 08, 29, 30, 31 |
| W-10 | 06, 16, 34 |
| W-11 | 19, 20, 12 |
| W-12 | 16, 22, 24, 28 |
| W-13 | 09, 15, 18, 25, 37, 38 |

## Units that touch the same files or tests

These units must be merged one at a time, each with `main` merged in first and the full suite green before the merge (lesson of `adjustable-quiet-hours`: parallel branches that edit the same file or the same fixture break each other silently; U-quiet-hours-09/10/11 and U-12/13 were ordered for this reason). Units listed as parallel in the diagram are parallel for the build, not for the merge.

| Shared file or test | Units, in merge order |
| --- | --- |
| `backend/pyproject.toml`, `backend/uv.lock` | 03, 04, 08, 33 |
| `backend/app/main.py`, `backend/app/config.py`, `backend/app/startup.py` | 04, 05, 08, 09, 15 |
| `backend/app/core/security.py` (markers) | 05, 12, 14 |
| `backend/app/routers/auth.py` | 11, 13, 14 |
| `backend/app/routers/settings.py` | 17, 34 |
| `backend/app/middleware.py` | 05, 15 |
| `backend/tests/test_route_inventory.py` | 05, 11, 13, 14, 17, 18, 34 |
| `docs/api/openapi.json` (generated; regenerate after each merge) | 05, 11, 13, 14, 17, 18, 34 |
| `backend/tests/db/conftest.py`, `backend/tests/conftest.py` | 08, then every later backend DB unit |
| `agents/mail-triage/migrations/versions/0008_web_auth.py`, `app/db/models.py` | 06 only; no later unit may edit 0008 |
| `agents/mail-triage/app/db/grants.sql`, `app/db/migrate.py`, `app/settings.py` | 07, 37 (grants), 38 (migrate) |
| `agents/mail-triage/tests/db/test_settings_migration.py`, `test_migrate_job.py`, `test_settings_grants.py` | 06, 07, 38 |
| `agents/mail-triage/app/runner.py`, `app/usecases/dispatch.py`, `app/core/settings_text.py` | 19, 20, 37 |
| `packages/schedule-policy/schedule_policy/policy.py`, `__init__.py`, `contract/settings_cases.json` | 17 only (and the agent image tests that run the fixture) |
| `apps/web/package.json`, `pnpm-lock.yaml` | 21, 22, 25 (any new dependency) |
| `apps/web/src/App.tsx`, `src/main.tsx` | 21, 23 |
| `apps/web/src/features/settings/SettingsForm.tsx` | 24, 27, 35, 36 |
| `apps/web/src/features/settings/SettingsPage.tsx` | 24, 25, 26 |
| `apps/web/src/pages/LoginPage.tsx` | 23, 36 |
| `apps/web/src/api/schema.d.ts` (generated) | 21, 34 (regenerate) |
| `apps/web/e2e/ui-states.spec.ts`, `apps/web/playwright.config.ts` | 28, 32, 35 |
| `apps/web/nginx.conf` | 29 only |
| `compose.yaml` | 03, 31 |
| `agents/mail-triage/compose.yaml` | 31 |
| `deploy/charts/app/values.yaml`, `values.schema.json` | 29, 30 |
| `deploy/charts/worker/templates/migration.yaml`, `README.md` | 30, 38 |
| `.github/workflows/ci.yml` | 03, 32 (02 and 28 only if a job changes) |
| `.github/workflows/mutation.yml` | 33 only |

Rule: if two units of one row are built in parallel, the second to finish rebases on `main` after the first merges and re-runs its full suite, then regenerates the generated files (`openapi.json`, `schema.d.ts`, lockfiles) instead of merging them by hand.

## Decisions needed

Not decided here; each needs a decision (ADR through `decision-gate`) before the named unit is built.

| # | Question | Why it matters | Units | Suggestion |
| --- | --- | --- | --- | --- |
| D-1 | How does the page learn the notice interval N for "within about N minutes"? The API contract (`/api/session`, `Settings`) has no such field; the agent's value is `POLL_INTERVAL_SECONDS`. | AC-13 and AC-28 need the real value on the page. | 04, 17, 26, 30 | A field `noticeIntervalMinutes` in `GET /api/session`, set from one chart value that the worker chart also uses. |
| D-2 | Fonts: ADR-0035 says Google Fonts with a system fallback, but the nginx CSP is `style-src 'self'` and `font-src 'self'`, which blocks them, and every visit would tell Google. | CSP is an acceptance criterion (AC-14). | 02, 21, 29 | Self-host the Bricolage Grotesque and Figtree files under `apps/web/public/fonts` and keep the CSP as it is. |
| D-3 | Name of the Telegram command that lifts the web lock (ADR-0033 says only "a command"). | The lock must be lifted in a way Marco can remember. | 20 | `/web_unlock`. |
| D-4 | Where the login page gets the account to name and the provider button label (the API allow-list has no public config route). | AC-24 needs the account named. | 23 | Build-time Vite variables per environment (no new route, no contract change). |
| D-5 | Refusal surface: the design makes the 400 and 403 of the callback static pages served by the api; the screens document describes banners on `/login`. | Words and focus behaviour (AC-24) differ. | 13, 23 | Keep the static pages with a "Back to sign in" link to `/login`; the login page shows banners only for `notice=expired`. |
| D-6 | Where the R2 draft lives across the provider round trip: the design says memory, the screens document says `sessionStorage`, and a top-level navigation drops memory. | The zone is low personal data; tab-scoped storage is the only way to keep the draft. | 36 | `sessionStorage`, values and version only, removed on sign-out or after 12 hours. |
| D-7 | Where the certificate expiry alert (at least 14 days ahead, W-9 delta) lives; it depends on the monitoring stack (ADR-0013) and the cluster. | Expiry is a W-9 control. | 30 | An optional `PrometheusRule` in the chart, enabled per environment once monitoring exists. |
| D-8 | What `updatedAt` and `updatedVia` are at version 0 (no row). | The OpenAPI schema and the "Using the default settings." line. | 17, 26 | Both `null` (nullable in the schema). |

## Open points

- Hosting (ADR-0012, ADR-0032): domain, certificate issuer, cluster and ingress controller are decided before staging. The build and all tests run against the prod-like stack and do not wait. The controller-specific ingress settings (8 KB body cap, TLS minimum, log format without the query string) are per-environment values (U-29); the pinned log format is settled with the controller.
- The agent run interval that the page quotes: the value comes from the agent configuration (`POLL_INTERVAL_SECONDS`, 60 in compose); how it reaches the page is D-1.
- Provider account protection (two-step verification or a passkey) is a condition for production (ADR-0033); R-1 is reviewed on 2027-05-10.
- The agent is not in the prod-like stack, so web notices, Undo and the lock are tested at agent level with a real database (U-19, U-20), and the api side of the lock in U-12 and U-13. A full chain test across both is part of staging.
- Documentation (phase 8) is not a unit here: the user-guide page for the settings page with screenshots, the API guide and the generated reference are written from what is built.
- Total: 38 units (33 in R1, 5 in R2), three above the target of about 35. Merging U-01 and U-02, or U-11 and U-12, would break single responsibility; the count is kept.

## Changes made during the build

Filled in while building, in the manner of `adjustable-quiet-hours`. Carried over as rules:

- Anything found by the challenge round (phase 6) gets its own fix unit `U-web-settings-<nn>` with the source of the finding named, and runs in parallel only when it shares no file with another.
- The first mutation run of U-33 is recorded here with run id and scores.
- Migration numbers are checked against `main` before each merge.
