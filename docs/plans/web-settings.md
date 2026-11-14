---
intent: INT-002
feature: web-settings
title: Web settings (login and settings page)
spec: docs/specs/web-settings.md
design: docs/design/web-settings-design.md
screens: docs/design/web-settings-screens.md
handoff: docs/design/web-settings-handoff.md
threat-model: docs/security/web-settings-threat-model.md
status: approved
approver: Marco
date: 2026-11-10
revision: 2 (ADR-0036 e-mailed code, ADR-0037 local-only, QA review of revision 1)
---

The second feature of INT-002. It adds a two-step login page (username, then a six-digit code sent by e-mail, ADR-0036) and a settings page in `apps/web`, a session and settings API in `backend` with a send-only SMTP mail sender, one more database role and schema (migration 0008 in the agent chain), web notices with Undo and lock in `agents/mail-triage`, and the local edge (nginx, local ingress with a private CA, NetworkPolicy, prod-like stack with a Caddy TLS edge and the mail catcher; ADR-0037). There is no identity provider, no OIDC library and no mock provider. Built in two releases (W5): R1 first, R2 later (marked per unit).

Done before the build and not a unit: the clickable prototype was built, reviewed and approved (PR #55; `docs/design/web-settings-handoff.md`, `docs/design/web-settings-prototype.html`). Its login page is superseded; its settings page is the reference for `/settings`. Unit U-01 reads the tokens from the hand-off.

Each unit gets its own git worktree and branch `feat/INT-002/web-settings/<nn>` and is built test-first: a failing test is shown before the implementation. A test is named after its criterion (`test_given_<x>_when_<y>_then_<z>` in Python, the same sentence as `it(...)` in Vitest and Playwright). Commits carry `Refs: INT-002` and `Unit: U-web-settings-<nn>`.

Common guardrails for every unit: `guardrail-python` + `guardrail-pytest` for Python, `guardrail-typescript` + `guardrail-vitest-rtl` for web code. Others are listed per unit.

## Test rules and levels

- Time, ids and codes are injected (U-03). `create_app(settings, *, clock, ids, codes, mailer)`; tests use `FakeClock`, a counting `FakeIds`, a scripted `FakeCodes` and a recording `FakeMailer`. An AST test (U-03) fails when `datetime.now`, `datetime.utcnow`, `time.time`, `date.today`, `uuid4`, `random.*` or `secrets.*` is called in any module of `backend/app` other than `clock.py`, `ids.py` and `codes.py`; no `now()` in SQL (expiry is decided in Python and passed as a parameter); no sleeps (barriers and the fake clock). The browser side injects its clock the same way.
- No real SMTP relay, Telegram or network. Backend tests use the fake mailer; the SMTP adapter is tested against an in-process STARTTLS test server (U-12); the prod-like stack uses the mail catcher on port 8025, from which tests read the code.
- Real PostgreSQL (testcontainers) for everything that touches `web_auth`, `settings` or a grant. The shared fixture of U-09 applies the agent migration chain as owner, then `grants.sql`, then connects as `web_settings_runtime`; no later unit edits the shared `conftest.py` files (they add fixtures in their own test modules).
- Canary values: the username `canary-user`, the code `424242`, the zone `Pacific/Kiritimati` and the SMTP password `canary-smtp-secret` must never appear in captured logs. One shared check in `backend/tests/conftest.py` (owned by U-03) fails any test that leaves a canary in a log record; unit tests that use the canaries on purpose (failure paths) rely on it. "No raw query string or secret in any log line" means: no line contains a canary, a cookie value, an `error_description`, or `?` followed by a query-parameter name.
- Levels named in the criteria: **unit** (pure function, no I/O), **db** (testcontainers PostgreSQL), **api** (in-process FastAPI app with fakes), **agent** (agent use case with fakes plus a real database), **component** (Vitest, Testing Library, axe with contrast off in jsdom), **playwright** (`ui-states` with a stubbed API, or `smoke` and `journey` against the prod-like stack), **chart** (`helm template`, kubeconform, kube-linter, a Python or Node test over the render), **image** (a built image or compose service started by the test), **ci** (workflow or config file read by a test).
- Pixel sizes, contrast and overflow are checked only in Playwright (U-36); component tests check semantics and behaviour, never class names.
- Coverage gates: backend and agent `pytest` run with `--cov-fail-under=90` (already in each `pyproject.toml`; enforced by the `backend` CI job and the agent's `components` CI check); the web gets `coverage.thresholds` of 90 in the Vitest config (U-28), enforced by `pnpm -r test` in the `web` job.
- Mutation: each pure security module is mutation-tested locally before its unit merges (baseline gate, score at least 85 % or every survivor on the unit's committed exclusion list `backend/mutation/<module>.exclusions`). Type annotations are excluded from mutation (CPython 3.14 does not evaluate them, the survivors of `adjustable-quiet-hours` were mostly this). U-44 only wires the scheduled workflow.

## Milestones and release gates

- **M1, API walking skeleton:** with fakes and a real database, sign in with a code (request, read from the fake mailer, verify), `GET /api/settings`, `PUT /api/settings` once, sign out. Units 02, 03, 04, 05, 06, 07, 09, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22 and the smoke test U-25. Everything after M1 hardens or adds to a working path.
- **M2, browser walking skeleton:** the same journey in the prod-like stack over HTTPS: sign in with the code read from the mail catcher, open `/settings`, save once (`smoke.spec.ts`, U-42). Needs M1 plus 01, 08, 28, 29, 30, 32, 37, 38, 39, 42.
- **R1 gates (the release does not ship without them):** U-24 (limits, W-7 and W-17 are open without it), U-13 and U-14 (security events and log hygiene, AC-20), U-26 and U-27 (web notices, Undo, lock: R-1 is defensible only with them), U-41 (NetworkPolicy and secrets), U-36 (accessibility), U-43 (journey), U-44 (mutation workflow). The certificate expiry alert (D-7) is also a gate for production, not for the build.

## Order and parallelism

```text
Start now (no dependency, parallel):  U-01 tokens + fonts   U-02 backend image + shared package   U-06 migration 0008   U-40 chart: local ingress
Backend       U-02 ─► U-03 clock/ids/codes + fakes ─► U-04 settings + start-up ─► U-05 HTTP surface + LimitGuard seam
              U-02 ─► U-10 pure: code hash, mask, digest, return_to   U-11 pure: sign-in time rules, session expiry   (mutation baseline each)
Database      U-06 ─► U-07 grants ─┬─► U-08 migrate job role list + WEB_ROLE_PASSWORD wiring
                                   └─► U-09 DB access + fixture + readiness (needs U-04)
Sign-in       U-12 mail sender (U-04) · U-13 security events (U-07, U-09, U-10) · U-14 logging hygiene (U-05)
              U-15 session store (U-05, U-09, U-11, U-13) · U-16 login request store (U-07, U-09, U-10, U-11)
              U-17 request-code (U-05, U-12, U-13, U-16) · U-18 verify-code (U-13, U-15, U-16) · U-19 CSRF, Origin, /api/session, logout (U-15)
Settings API  U-20 read (models, GET, RULES, openapi) (U-05, U-09, U-15) ─► U-21 write repository (U-07, U-09, U-20) ─► U-22 PUT route (U-19, U-21)
              U-23 places route (U-05, U-15)      U-24 limits (U-05, U-13, U-17, U-18)  [R1 gate]
              U-25 API walking skeleton (U-18, U-19, U-22)  ══► M1
Agent         U-26 web notices (U-06, U-07) ─► U-27 notice buttons + /web_unlock          (parallel with Backend and Web)
Web           U-28 shell + API client (U-01, U-20)    U-29 primitives (U-01, parallel)
              U-30 login: username and code steps (U-28, U-29, openapi of U-17, U-18) ─► U-31 login: resend, countdown, refusals
              U-32 settings form with slots (U-22, U-28, U-29) ─► U-33 ZoneCombobox (U-23) · U-34 save feedback + zone preview · U-35 conflict
              U-36 ui-states (U-30..U-35)
Edge          U-37 prod-like TLS edge + nginx exact routes (U-02) ─► U-38 prod-like mail catcher + SMTP (U-12) · U-39 prod-like TLS database (U-08, U-09)
              U-41 chart: NetworkPolicy, replicas, secrets (U-08, U-40)
              U-42 CI sequence + setup + smoke (U-30, U-32, U-37, U-38, U-39)  ══► M2
              U-43 journey (U-33, U-34, U-35, U-36, U-42)      U-44 mutation wiring (U-10, U-11, U-24)
R2            U-45 reset backend (U-22) ─► U-46 reset web (U-32)   U-47 draft kept (U-30, U-32)   U-48 wrong-code alert (U-13, U-26; R1 since ADR-0039)   U-49 audit retention purge (U-07, U-08)
```

Build-green rules (lessons of `adjustable-quiet-hours`, section "Changes made during the build"):

- U-02 wires the shared package into the backend (lockfile, image, compose, CI) before any backend code imports it, as U-quiet-hours-01b did for the agent.
- Migration 0008 is the first migration of R1 (U-06); the challenge fixes add 0009 (U-56, merged first), 0010 (U-53) and 0011 (U-54). The R2 purge adds no migration. If another migration lands first, rename before merge; do not renumber after.
- A unit that adds an environment variable or a role must carry every consumer of it in the same PR: U-08 carries `WEB_ROLE_PASSWORD` in the job, the agent's compose file, the CI `runtime-role` job's `.env` line and the worker chart's Secret together, so `main` stays green. The same for U-37: the removal of `proxy_pass` from the web image and the new edge arrive together with the update of the existing `e2e` job.
- A one-shot compose service (migrate) is not part of `up --wait` (it exits and counts as failed). The CI job runs it with `docker compose run --rm` before `up --wait` (U-42).
- The R1 build exposes no R2 surface: U-05 (no `/api/settings/reset` in the route inventory and in `openapi.json`), U-32 (no Reset button in the DOM) and U-43 (the path answers 404 through the edge). U-45 and U-46 add them together with their tests.

## Units

### U-web-settings-01: Pebble tokens, self-hosted fonts and contrast test (R1)

- Layer: web
- Contract: `packages/tokens/tokens.json` replaces the placeholder with the Pebble values of the hand-off (colours with a light and dark value: surface, surface-raised, text, text-muted, border, divider, primary, primary-contrast, danger, danger-soft, success, success-soft, focus; radius 999 / 14 / 24 px; soft shadow; spacing and type steps; motion 200 ms press, 250 ms enter, spring curve, removed under reduced motion) through `design-tokens-bridge`. Bricolage Grotesque and Figtree are self-hosted as `woff2` files under `packages/tokens/fonts/` with their OFL licence files (D-2: the CSP blocks Google Fonts); `build.mjs` generates `@font-face` rules with relative URLs and regenerates `tokens.css` and `theme.native.json`. The contrast test covers text pairs at 4.5:1 and border, focus and control pairs at 3:1.
- Files: `packages/tokens/tokens.json`, `packages/tokens/tokens.css` (generated), `packages/tokens/theme.native.json` (generated), `packages/tokens/build.mjs`, `packages/tokens/contrast.test.mjs`, `packages/tokens/fonts/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-tailwind, guardrail-a11y, guardrail-vite
- Criteria:
  1. Given `tokens.json`, When validated, Then every colour has a light and a dark value, names are semantic and the placeholder description is gone (type: happy; level: unit).
  2. Given text on surface and on surface-raised, text-muted on both, primary-contrast on primary, danger on danger-soft, success on success-soft, in both modes, When measured, Then each pair is at least 4.5:1 (AC-22) (type: a11y; level: unit).
  3. Given border, focus ring and control edge against their adjacent surface in both modes, When measured, Then each is at least 3:1 (AC-23) (type: a11y; level: unit).
  4. Given a token that is 4.49:1 and one that is 4.50:1, When the test runs, Then the first fails naming the pair and the mode, the second passes (type: error; level: unit).
  5. Given a changed `tokens.json` without regenerated files, When `node packages/tokens/build.mjs --check` runs, Then it fails (type: error; level: ci).
  6. Given the motion tokens, When read, Then the longest duration is 250 ms and a reduced-motion value of 0 exists (type: edge; level: unit).
  7. Given the generated CSS, When read, Then every `@font-face` URL is relative, no `https://` URL appears, and every referenced font file exists with a licence file beside it (D-2, AC-14) (type: security; level: unit).
  8. Given `apps/web/src`, When searched for hex colours, `rgb(` and arbitrary Tailwind values, Then there is no hit outside the tokens package (type: edge; level: ci).

### U-web-settings-02: Backend image with the shared package (R1)

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
  4. Given the build context, When the image is built, Then `.env`, `.git` and `node_modules` are not in any layer (type: security; level: image).
  5. Given hadolint and Trivy in the `images` job, When run on the new image, Then no warning and no new High or Critical finding (type: security; level: ci).
  6. Given `docker compose --profile dev config` and `--profile test config`, When rendered, Then `api-dev` and `api-test` still resolve, and the existing backend suite and `e2e` job are green (type: happy; level: ci).

### U-web-settings-03: Clock, IdSource, CodeSource, fakes and the canary log check (R1)

- Layer: backend
- Contract: `Clock.now() -> datetime` (aware UTC; `SystemClock`), `IdSource` (`token(nbytes)`, `session_id()`, `login_request_id()`, `request_id()`), `CodeSource.six_digits() -> str` (`secrets`), in `app/clock.py`, `app/ids.py`, `app/codes.py`; test fakes `FakeClock` (settable), `FakeIds` (counting), `FakeCodes` (scripted) in `backend/tests/fakes.py`; the canary log check in `backend/tests/conftest.py`; the AST rule test.
- Files: `backend/app/clock.py`, `backend/app/ids.py`, `backend/app/codes.py`, `backend/tests/fakes.py`, `backend/tests/conftest.py`, `backend/tests/test_time_and_randomness_rule.py`
- Depends on: U-web-settings-02
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given `SystemClock.now()`, When called, Then the result is timezone-aware UTC; `FakeClock` returns exactly what was set and moves only when told to (type: happy; level: unit).
  2. Given the production `IdSource`, When it makes 1000 tokens of 32 bytes, Then all are distinct, 43 URL-safe characters long and come from `secrets` (type: security; level: unit).
  3. Given the production `CodeSource`, When it makes 10000 codes, Then each is exactly six decimal digits including leading zeros, and a code below 100000 occurs (no integer truncation) (type: edge; level: unit).
  4. Given `FakeCodes(["123456", "654321"])`, When asked three times, Then the first two values, then a clear error (type: error; level: unit).
  5. Given every module of `backend/app`, When parsed with `ast`, Then `datetime.now`, `datetime.utcnow`, `time.time`, `date.today`, `uuid4`, `random.*` and `secrets.*` are called only in `clock.py`, `ids.py` and `codes.py`; a planted call in another module makes the test fail (type: security; level: unit).
  6. Given a test that logs a canary (`canary-user`, `424242`, `Pacific/Kiritimati`, `canary-smtp-secret`), When it ends, Then the shared check fails that test and names the canary and the logger (type: security; level: unit).
  7. Given the canary check and a test that did not log a canary, When it ends, Then it passes (type: happy; level: unit).

### U-web-settings-04: Settings and start-up validation (R1)

- Layer: backend
- Contract: `Settings` gains every value the feature needs, defined once here: username, e-mail address, SMTP host, port, user, password and `smtp_starttls`, code-hash key, CSRF key, username-hash key, public origin, database URL (asyncpg, `ssl` setting), `notice_interval_minutes`, and the limits (`rate_limit_per_minute` 30, `body_limit_bytes` 8192, `code_ttl_seconds` 600, `resend_cooldown_seconds` 60, `codes_per_hour` 5, `max_attempts` 5, `open_login_request_cap`, `idle_seconds` 1800, `absolute_seconds` 43200, trusted proxy CIDRs and hops). `validate_startup(settings)` raises `ConfigurationError` naming the field, never the value; `create_app(settings, *, clock, ids, codes, mailer)` calls it. The cookie lifetimes are fixed here: `__Host-login` Max-Age 600, `__Host-session` Max-Age 43200.
- Files: `backend/app/config.py`, `backend/app/startup.py`, `backend/app/main.py`, `backend/tests/test_startup.py`
- Depends on: U-web-settings-03
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given a complete valid configuration, When checked, Then no error (type: happy; level: unit).
  2. Given an empty username, When the app is created, Then `ConfigurationError` names `username`; the same with `ENV=test` (AC-4) (type: error; level: api).
  3. Given a missing e-mail address, `not-an-address` and `a@b@c`, When checked, Then each is refused naming `email_address` (AC-4, W-1) (type: error; level: unit).
  4. Given a missing SMTP host, port, user or password, When checked, Then each is refused naming the field (AC-4, W-16) (type: error; level: unit).
  5. Given `smtp_starttls` false or implicit TLS without STARTTLS, When checked, Then refused (AC-4, W-14) (type: security; level: unit).
  6. Given a code-hash key of 31 bytes, one of 32 bytes, and two keys that are equal (code-hash, CSRF, username-hash pairwise), When checked, Then 31 and equal are refused, 32 passes (AC-4, W-1) (type: security; level: unit).
  7. Given a public origin that is not `https`, When checked, Then refused (AC-18) (type: security; level: unit).
  8. Given a refused start with canary values in the secret fields, When logs and the exception text are captured, Then no canary value appears, only field names (W-15) (type: security; level: api).
  9. Given the limit settings, When read, Then each default equals the spec value (30, 8192, 600, 60, 5, 5, 1800, 43200) and tests can lower them (C-4) (type: happy; level: unit).
  10. Given `pyproject.toml`, When read, Then `--cov-fail-under=90` is in the pytest options and the `backend` CI job runs `uv run pytest` (type: happy; level: ci).

### U-web-settings-05: HTTP surface: errors, headers, request id, LimitGuard seam, route inventory (R1)

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
  7. Given a route outside the allow-list, a route without a `public` or `session` marker, and `/api/settings/reset`, When the inventory runs, Then each fails naming the path (AC-15; the R1 build has no R2 surface) (type: security; level: unit).
  8. Given a route with the default `LimitGuard`, When called, Then it passes; Given a guard that raises, Then the response is the 429 problem with an integer `Retry-After` and the body names no limit or client (type: edge; level: api).
  9. Given `uv run python -m app.export_openapi --check`, When run, Then it passes and every exported path is on the allow-list (AC-15) (type: happy; level: ci).

### U-web-settings-06: Migration 0008: web_auth, web guard line, contract version, notice record (R1)

- Layer: backend (database; agent migration chain)
- Contract: migration `0008` in `agents/mail-triage/migrations`: schema `web_auth` with `login_request` (id, username key, code hash, `expires_at`, attempts, `created_at` (the request time, which starts the cooldown), `sent_at` (empty when the send failed; only sent codes count towards the hourly cap), `dead_at`; rows are marked dead when replaced or used and kept for one hour so the hourly cap can be counted), `session` (hashed id, hashed username, `last_seen_at`, `absolute_expires_at`), `security_event` (kind from a CHECK-constrained set, result, hashed username or null, request id, client key, window; no free text) and `web_lock` (single row); the web line in the guard of 0006 (`session_user = 'web_settings_runtime'` gives channel `web`, `updated_by` must match `^web:[0-9a-f]{32}$`, `version = old + 1`); the cursor for web notices in `poll_state`; the notice token record table; `settings.contract_version()`; every new function revoked from `PUBLIC`. Grants are not here (U-07).
- Files: `agents/mail-triage/migrations/versions/0008_web_auth.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/tests/db/test_web_auth_migration.py`, `agents/mail-triage/tests/db/test_settings_migration.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given revision 0007 with settings data, When migrated to 0008, Then the `web_auth` tables, the cursor column and the notice table exist, data is unchanged and models match the schema (no drift) (type: happy; level: db).
  2. Given 0008, When downgraded, Then schema, tables, column, function and the web guard line are gone, the 0006 guard works as before, and upgrading again is clean (type: edge; level: db).
  3. Given a write by session user `web_settings_runtime` (created in the test), When it updates the row with a valid `updated_by`, Then `updated_via` is `web` and the audit record has `db_role` web (AC-9, W-10) (type: happy; level: db).
  4. Given a write by the web role with `updated_by` of `telegram:1`, `web:` plus 31 hex, upper-case hex or empty, When executed, Then SQLSTATE 42501 for each (AC-17, W-10) (type: security; level: db).
  5. Given the web role with a version of old plus 2, and one claiming `updated_via = 'telegram'`, When executed, Then 42501 (AC-17) (type: security; level: db).
  6. Given the 0006 guard tests for the agent role and the owner, When run, Then they pass unchanged (type: happy; level: db).
  7. Given `settings.contract_version()`, When called, Then it returns the schema's integer constant, and no function added by 0008 has `PUBLIC` execute (W-8) (type: security; level: db).
  8. Given `security_event`, `login_request` and `session`, When their columns are inspected, Then kinds are a CHECK set, hashes are fixed-length, attempts is bounded 0 to 5 and there is no unbounded text column (W-13, W-15) (type: security; level: db).
  9. Given `web_lock`, When a second row is inserted, Then it is refused (ADR-0033) (type: edge; level: db).
  10. Given the notice token record, When two records with the same token are inserted, Then the second is refused (ADR-0033) (type: edge; level: db).

### U-web-settings-07: Grants for the web role and the agent's new rights (R1)

- Layer: backend (database)
- Contract: `grants.sql` (still the one source) gains `web_settings_runtime`: `SELECT` on `settings.schedule`; `INSERT` and `UPDATE` limited to the columns `(id,) zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by`; execute on `settings.contract_version()`; on `web_auth`: `login_request` insert/select/update/delete, `session` insert/select/update/delete, `security_event` insert/select, `web_lock` select; nothing on `public`, nothing on `settings_change`. The agent role gains `INSERT, UPDATE, SELECT` on `web_auth.web_lock`, the rights it needs on the notice token table and the cursor (`poll_state` is already granted) and nothing else in `web_auth`.
- Files: `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/tests/db/test_web_role_grants.py`, `agents/mail-triage/tests/db/test_settings_grants.py`
- Depends on: U-web-settings-06
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the web role, When it selects and updates the allowed columns and inserts the first row of `settings.schedule`, Then each works (type: happy; level: db).
  2. Given the web role, When it updates any column outside the list, or deletes or truncates `settings.schedule`, Then 42501 (AC-17) (type: security; level: db).
  3. Given `mail_item`, `alert`, `draft`, `oauth_token`, `audit_log`, `poll_state`, `catchup_state`, `overview_log`, `conversation` and `alembic_version`, When the web role selects from each, Then 42501 (AC-17, W-8) (type: security; level: db).
  4. Given `settings.settings_change`, When the web role selects, inserts, updates, deletes or truncates, Then 42501 (AC-17) (type: security; level: db).
  5. Given the web role, When it runs `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` or `SET session_replication_role`, Then 42501 (AC-17) (type: security; level: db).
  6. Given `web_auth`, When the web role updates `web_lock`, updates `security_event`, or deletes `security_event`, Then 42501 (type: security; level: db).
  7. Given the agent role, When it inserts and updates `web_auth.web_lock`, Then it works; when it reads or writes `session`, `login_request` or `security_event`, Then 42501 (ADR-0033) (type: security; level: db).
  8. Given the real agent role `mail_triage_runtime`, When it inserts and updates the notice token record and the cursor, Then it works; the web role on both gets 42501 (ADR-0033) (type: security; level: db).
  9. Given `grants.sql` run twice, When compared, Then the same grants result; the 0006 grant tests for the agent role pass unchanged (type: edge; level: db).

### U-web-settings-08: Migrate job creates the roles from a list; WEB_ROLE_PASSWORD everywhere (R1)

- Layer: infra (database)
- Contract: `migrate.py` creates the runtime roles from a list (the agent role and the web role) with the SCRAM, no-membership and no-replication rules of ADR-0030; `WEB_ROLE_PASSWORD` is a new required setting of the job. The same PR carries every consumer: the agent's `compose.yaml` migrate service, the CI `runtime-role` job's `.env` line, the worker chart's migration Secret key, Job env and README (sealing by standard input), so nothing on `main` goes red.
- Files: `agents/mail-triage/app/db/migrate.py`, `agents/mail-triage/app/settings.py`, `agents/mail-triage/compose.yaml`, `.github/workflows/ci.yml`, `deploy/charts/worker/templates/migration.yaml`, `deploy/charts/worker/README.md`, `agents/mail-triage/tests/db/test_migrate_job.py`
- Depends on: U-web-settings-07
- Parallel: no
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-compose, guardrail-helm, guardrail-kubernetes
- Criteria:
  1. Given the job with two roles and two passwords, When it runs, Then both roles exist with SCRAM verifiers computed client side, `NOREPLICATION NOBYPASSRLS`, no membership, and no statement the server received contains a clear password (ADR-0030) (type: security; level: db).
  2. Given a missing `WEB_ROLE_PASSWORD`, When the job runs, Then it exits non-zero naming the key, not a value, before any role is changed (type: error; level: db).
  3. Given the web role has a role membership or REPLICATION, When the job runs, Then REPLICATION is reset and the membership makes the job exit 6 naming the role (type: error; level: db).
  4. Given the job runs twice, When compared, Then the second run changes nothing (type: edge; level: db).
  5. Given `agents/mail-triage/compose.yaml`, When rendered with and without the variable, Then the migrate service passes `WEB_ROLE_PASSWORD` by reference and no literal value exists (type: security; level: ci).
  6. Given the CI `runtime-role` job, When read, Then its `.env` step writes `WEB_ROLE_PASSWORD` and the job still passes with the 19 forbidden statements of the agent role (type: happy; level: ci).
  7. Given the rendered worker chart, When read, Then the migration Secret has the `WEB_ROLE_PASSWORD` key, the Job env references it, a missing key fails the Job naming the key, and the README seals by standard input without `--from-literal=` (ADR-0029) (type: security; level: chart).
  8. Given the rendered Job and Secret, When searched, Then the web password is in no values file or ConfigMap (type: security; level: chart).

### U-web-settings-09: Database access, shared fixture and readiness (R1)

- Layer: backend
- Contract: async engine and session factory for the web role with `asyncpg` (`sqlalchemy[asyncio]`); the `ssl` argument is an `ssl.SSLContext` with `verify-full` behaviour (CA from the configured file, `check_hostname`, `CERT_REQUIRED`), the start-up check refuses any other mode in production; statement timeout from settings; `/readyz` compares `settings.contract_version()` with the expected constant instead of the agent's Alembic head; start-up removes expired `login_request` and `session` rows using `Clock`; the shared DB fixture (applies the agent chain as owner, `grants.sql`, connects as the web role, clean state per test) in `backend/tests/db/conftest.py`, which no later unit edits.
- Files: `backend/app/db.py`, `backend/app/routers/health.py`, `backend/app/startup.py`, `backend/pyproject.toml`, `backend/tests/db/conftest.py`
- Depends on: U-web-settings-04, U-web-settings-06, U-web-settings-07
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-fastapi
- Criteria:
  1. Given a migrated database, When `/readyz` is called, Then 200 (type: happy; level: db).
  2. Given a database whose `contract_version()` differs, When `/readyz` is called, Then 503 with a generic body (type: error; level: db).
  3. Given the database is down and the URL contains the canary password, When `/readyz` is called, Then 503 and the log has the error class and SQLSTATE only, no URL, no canary (type: security; level: db).
  4. Given the TLS settings, When the engine is built, Then the context has `check_hostname` true and `verify_mode` `CERT_REQUIRED`; production settings with `ssl` off, `require` or `verify-ca` are refused naming `database_url` (W-8, W-9) (type: security; level: unit).
  5. Given expired and valid rows in `login_request` and `session` and a `FakeClock`, When the app starts, Then only the expired rows are removed (type: edge; level: db).
  6. Given the source tree, When searched for `now()` and `CURRENT_TIMESTAMP` in SQL text, Then there is no hit (type: edge; level: unit).
  7. Given a statement slower than the timeout, When run, Then it is cancelled and the request ends 503 (W-7) (type: error; level: db).
  8. Given two tests in a row, When each uses the fixture, Then each starts from a clean schema state (type: edge; level: db).

### U-web-settings-10: Pure rules for the code: hash, mask, username digest, return path (R1)

- Layer: backend (pure module; mutation-gated)
- Contract: `app/auth/code_hash.py` (`hash_code(key, request_id, code) -> bytes` HMAC-SHA-256 over request id and code, `verify_code(...)` with `hmac.compare_digest`), `app/auth/mask.py` (`mask_address("marco@example.com") -> "m***@example.com"`), `app/auth/digest.py` (`username_digest(key, username) -> 32 lower-case hex`, also the `updated_by` value `web:<32 hex>`), `app/auth/return_to.py` (`safe_return_to(value) -> "/settings"`). All import only the standard library, carry the marker `# pure module (mutation-gated)` and are checked by `tests/test_pure_modules.py`. This unit also adds the local mutation runner `backend/mutation/run.py <module>` (annotations excluded).
- Files: `backend/app/auth/code_hash.py`, `backend/app/auth/mask.py`, `backend/app/auth/digest.py`, `backend/app/auth/return_to.py`, `backend/tests/auth/test_code_rules.py`, `backend/tests/test_pure_modules.py`, `backend/mutation/run.py`
- Depends on: U-web-settings-02
- Parallel: yes (with U-03 to U-05)
- Guardrails: guardrail-python, guardrail-pytest, guardrail-oauth2-oidc
- Criteria:
  1. Given a key, request id and code, When hashed twice, Then the result is identical, 32 bytes, differs for another key, another request id or another code (W-1) (type: happy; level: unit).
  2. Given the right code and `123456` vs `123457`, When verified, Then true and false; Given a code with spaces or letters, Then false without an exception (AC-3) (type: edge; level: unit).
  3. Given the verifier, When timed with a matching and a non-matching code of the same length, Then it calls `hmac.compare_digest` (checked by patching it) and never `==` on the digests (W-1) (type: security; level: unit).
  4. Given `marco@example.com`, `a@example.com` and `very.long.name@sub.example.org`, When masked, Then `m***@example.com`, `a***@example.com`, `v***@sub.example.org`; the full local part never appears (W-15) (type: security; level: unit).
  5. Given `username_digest` with two keys and two usernames, When called, Then results differ, are 32 lower-case hex characters, stable for equal input, and the plain username is not a substring (W-10, W-15) (type: security; level: unit).
  6. Given `return_to` values `https://evil.example`, `//evil.example`, `/\evil`, `javascript:alert(1)`, `/settings/../x`, `/other`, an empty value and `None`, When processed, Then `/settings` each; `/settings` stays `/settings` (AC-6, W-2) (type: security; level: unit).
  7. Given every module of this unit, When their imports are read, Then none imports FastAPI, SQLAlchemy, httpx or the network; the marker test lists them (type: edge; level: unit).
  8. Given the baseline mutation run of the four modules, When it finishes, Then the score is at least 85 % or every survivor is on the committed `backend/mutation/<module>.exclusions` list with a reason (type: security; level: unit).

### U-web-settings-11: Pure rules for time: code life, attempts, cooldown, hourly cap, session expiry (R1)

- Layer: backend (pure module; mutation-gated)
- Contract: `app/auth/code_rules.py` (`code_expired(created_at, now, ttl)`, `attempts_exhausted(attempts, max)`, `register_wrong(attempts, max) -> (attempts, dead)`, `cooldown_remaining(last_requested_at, now, cooldown) -> int` over every request, `hourly_cap_reached(sent_times, now, cap)` over sent codes only) and `app/auth/expiry.py` (`idle_expired`, `absolute_expired`, `next_idle_expiry`). Standard library only, marker as in U-10.
- Files: `backend/app/auth/code_rules.py`, `backend/app/auth/expiry.py`, `backend/tests/auth/test_time_rules.py`, `backend/mutation/code_rules.exclusions`
- Depends on: U-web-settings-02
- Parallel: yes (with U-10)
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given a code created at 14:00:00 with a 600 s life, When asked at 14:09:59 and 14:10:00, Then not expired, then expired (AC-3) (type: edge; level: unit).
  2. Given a code with 4 and 5 wrong attempts, When one more wrong code is registered, Then the fifth wrong attempt kills the code (attempt 5 dead, attempt 4 alive) and a sixth is refused without a comparison (AC-3, AC-5) (type: edge; level: unit).
  3. Given the last request at 14:00:00 (sent or not) and a 60 s cooldown, When asked at 14:00:59 and 14:01:00, Then 1 second remains, then 0 (AC-5, AC-31) (type: edge; level: unit).
  4. Given sent codes at 13:00:01 and later (failed sends are not in the list), When asked at 14:00:00 and 14:00:01, Then the first send still counts, then it falls out of the hour; with 4 sent codes in the hour the cap is not reached, with 5 it is (AC-5, AC-31) (type: edge; level: unit). Superseded by D-16 and U-53: every request counts from `created_at`, sent or not.
  5. Given a session last seen at 14:00:00, When asked at 14:29:59 and 14:30:00, Then valid, then idle-expired (AC-7) (type: edge; level: unit).
  6. Given a session created at 08:00:00 with activity every 20 minutes, When asked at 19:59:59 and 20:00:00, Then valid, then absolute-expired (AC-7) (type: edge; level: unit).
  7. Given naive datetimes, When passed in, Then an error (type: error; level: unit).
  8. Given every module of this unit, When imports are read, Then only the standard library (type: edge; level: unit).
  9. Given the baseline mutation run, When it finishes, Then the score is at least 85 % or every survivor is on the committed exclusion list (type: security; level: unit).

### U-web-settings-12: Mail sender port, SMTP adapter and fake (R1)

- Layer: backend
- Contract: port `MailSender.send_code(address, code, expires_at) -> None` raising `MailError` (no cause text) on any failure; `SmtpMailSender` using `aiosmtplib` (decided here: async, STARTTLS with `start_tls=True` and certificate validation, maintained; pinned in `pyproject.toml` within the dependency cooldown); `FakeMailer` records messages. The message is plain text: the code, its validity in minutes, no link, no request details, a subject without the code. The `aiosmtplib` logger is pinned to WARNING.
- Files: `backend/app/mail/sender.py`, `backend/app/mail/smtp.py`, `backend/app/mail/message.py`, `backend/tests/mail/test_smtp.py`, `backend/pyproject.toml`
- Depends on: U-web-settings-04
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-tls-certificates
- Criteria:
  1. Given a code `424242` and an expiry, When the message is built, Then the body has the code and "valid for 10 minutes", no `http`, no `<a`, no URL, and the subject does not contain the code (AC-29, W-14) (type: security; level: unit).
  2. Given the in-process test server that offers STARTTLS with a certificate from the test CA, When a message is sent, Then it arrives after the upgrade and the credentials were sent only after it (AC-29) (type: happy; level: unit).
  3. Given a server without STARTTLS, When a message is sent, Then `MailError` and nothing was sent, no downgrade to plain text (AC-29, W-14) (type: security; level: unit).
  4. Given a server certificate from an untrusted CA or for another host name, When a message is sent, Then `MailError` (AC-29, W-14) (type: security; level: unit).
  5. Given a refused login, a timeout and a dropped connection, When sending, Then `MailError` each, whose text contains neither the address, the code, the password nor the server reply (W-15, W-16) (type: security; level: unit).
  6. Given a failing send with canaries for code and password, When logs are captured, Then no canary appears and the `aiosmtplib` logger is at WARNING (W-15, W-16) (type: security; level: unit).
  7. Given the send timeout from settings, When the server stalls, Then the call ends at the timeout with `MailError` (type: error; level: unit).
  8. Given `FakeMailer`, When used, Then it records address, code and expiry and can be told to fail (type: happy; level: unit).

### U-web-settings-13: Security event store (R1; the alert is R2)

- Layer: backend
- Contract: `SecurityEvents.record(kind, request_id, client, username_hash=None)` writes `web_auth.security_event`; kinds `code_refused` (wrong, expired, used, exhausted, no cookie; the R2 alert counts these), `code_request_refused` (cooldown, hourly cap), `mail_failed`, `session_start`, `session_end`, `csrf_refused`, `rate_limited`, `lock_refused`; one row per kind, client and window (`floor(clock.now() / 60)`); an unknown username is stored only as its digest (U-10); one structured log line per recorded event with kind, result, client class and request id. Changed by U-54: a repeat of `code_refused` increments `count`; U-63 adds `code_invalid`.
- Files: `backend/app/security_events.py`, `backend/tests/test_security_events.py`
- Depends on: U-web-settings-07, U-web-settings-09, U-web-settings-10
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-fastapi
- Criteria:
  1. Given a `code_refused` event for the canary username, When recorded, Then the row has kind, result, request id, client and the digest of the username, and the canary appears nowhere in the table or the log (AC-20, W-13, W-15) (type: security; level: db).
  2. Given ten identical events from one client in one window, When recorded, Then one row exists; after the `FakeClock` crosses the window boundary (59.9 s then 60.0 s) a second row is added (AC-20) (type: edge; level: db).
  3. Given two different kinds from one client in one window, When recorded, Then both are kept (type: edge; level: db).
  4. Given a recorded event, When the log is captured, Then one line has kind, result and request id and no code, cookie, username or address (AC-20, W-15) (type: security; level: db).
  5. Given an unknown kind string, When recorded, Then it is refused before the database (type: error; level: unit).
  6. Given the insert fails, When an event is recorded inside a refusal, Then the caller still returns its refusal and the log has the error class only (type: error; level: db).
  7. Given a `mail_failed` event, When recorded, Then it carries no address and no error text (AC-29, W-16) (type: security; level: db).

### U-web-settings-14: Logging hygiene (R1)

- Layer: backend
- Contract: the uvicorn access log is off (image command without `--access-log`), request logging records method, path template, status and request id and never the query string, and the `httpx`, `httpcore` and `aiosmtplib` loggers are pinned to WARNING in `app/logging_setup.py`.
- Files: `backend/app/logging_setup.py`, `backend/app/main.py`, `backend/Dockerfile`, `backend/tests/test_logging_hygiene.py`
- Depends on: U-web-settings-05
- Parallel: yes (with U-12, U-13)
- Guardrails: guardrail-fastapi, guardrail-docker
- Criteria:
  1. Given `GET /auth/anything?code=424242&q=Pacific/Kiritimati`, When served, Then no captured log line contains a canary, `code=`, `q=` or any query-parameter name after a `?` (AC-20, W-13, W-15) (type: security; level: api).
  2. Given a request with a cookie holding a canary value, When served, Then the cookie value is in no log line (W-15) (type: security; level: api).
  3. Given the image command, When read, Then the access log is disabled (type: security; level: ci).
  4. Given the app is created, When the loggers are read, Then `httpx`, `httpcore` and `aiosmtplib` are at WARNING (type: security; level: unit).
  5. Given an unhandled error on a request with a canary body, When logged, Then the line has the class and request id only (AC-15) (type: security; level: api).
  6. Given one request, When served, Then exactly one request line is logged with the request id and the matched path template, not the raw path with ids (type: happy; level: api).

### U-web-settings-15: Session store, cookie and lock check (R1)

- Layer: backend
- Contract: `SessionStore.create(username_hash, now) -> (cookie_value, Session)` (new random id each time through `IdSource`; only the hash of the id is stored), `get(cookie_value, now)`, `touch`, `delete`; `session_cookie(value)` builds `__Host-session` (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, Max-Age 43200); `require_session` (marker `session`) uses the pure rules of U-11; while `web_auth.web_lock` is set every lookup answers 401 and deletes the sessions.
- Files: `backend/app/auth/session.py`, `backend/app/core/security.py`, `backend/tests/auth/test_session.py`
- Depends on: U-web-settings-05, U-web-settings-09, U-web-settings-11, U-web-settings-13
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a created session, When the cookie is built, Then name `__Host-session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, Max-Age 43200, a 256-bit value (AC-7, W-3) (type: security; level: unit).
  2. Given a session last seen at 14:00:00 (`FakeClock`), When used at 14:29:59 and 14:30:00, Then accepted, then 401 (AC-7) (type: edge; level: db).
  3. Given activity every 20 minutes from 08:00:00, When used at 19:59:59 and 20:00:00, Then accepted, then 401 (AC-7) (type: edge; level: db).
  4. Given two sign-ins, When both create sessions, Then the ids differ, and a cookie presented before sign-in is never adopted (AC-7, W-3) (type: security; level: db).
  5. Given the table read as the owner, When inspected, Then only the hash of the id and the username digest are stored (W-3) (type: security; level: db).
  6. Given no cookie, an unknown cookie or an expired session, When a protected route is called, Then 401 with the generic body (AC-2) (type: error; level: api).
  7. Given `web_lock` set, When a valid session calls a protected route, Then 401, the sessions are deleted and a `lock_refused` event is recorded once per window (AC-27, ADR-0033) (type: security; level: db).
  8. Given each authorised request, When served, Then `last_seen_at` moves to the clock's now (type: happy; level: db).
  9. Given the logout path, When a session is deleted, Then a `session_end` event is recorded (AC-20) (type: happy; level: db).

### U-web-settings-16: Login request store (R1)

- Layer: backend (database)
- Contract: `LoginRequests.create(username_key, code, now, cap) -> LoginRequest` marks any live request of that username dead and inserts a new row with the code hash (U-10) and expiry; `check(request_id, code, now) -> Verdict` in one transaction (`SELECT ... FOR UPDATE`): `Ok` (row marked dead, single use), `Wrong(attempts_left)`, `Dead`; `mark_sent(request_id, now)` (called only after a successful send), `last_requested_at(username_key)` (every request), `sent_in_last_hour(username_key, now)` (only rows with `sent_at`); open rows capped; rows older than one hour are removed on insert.
- Files: `backend/app/auth/login_requests.py`, `backend/tests/auth/test_login_requests.py`
- Depends on: U-web-settings-07, U-web-settings-09, U-web-settings-10, U-web-settings-11
- Parallel: yes (with U-12 to U-15)
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a created request and the right code at 9:59 after creation, When checked, Then `Ok` and the row is dead; the same code again is `Dead` (AC-3) (type: happy; level: db).
  2. Given the right code at 10:00 after creation (`FakeClock`), When checked, Then `Dead` (expired) (AC-3) (type: edge; level: db).
  3. Given five wrong codes, When the fifth is checked, Then it returns `Dead`, and the right code after that is `Dead`; after four wrong codes the right code is still `Ok`; `attempts_left` counts 4, 3, 2, 1 (AC-3, AC-5) (type: edge; level: db).
  4. Given an old code and a newer code for the same username, When the old one is checked, Then `Dead` (replaced) (AC-3) (type: security; level: db).
  5. Given a request id of another browser, an unknown id and `None`, When checked, Then `Dead` for each, with no attempt counted on any other row (AC-3, W-1) (type: security; level: db).
  6. Given two checks of the right code at the same time with a barrier, When both run, Then exactly one is `Ok` (single use) (AC-3) (type: security; level: db).
  7. Given five codes created and marked sent within one hour, When `sent_in_last_hour` is read, Then 5 and the cap logic of U-11 refuses the sixth; a send 60 min 1 s old is no longer counted, one 59 min 59 s old is (AC-31) (type: edge; level: db).
  8. Given five requests whose send failed (never marked sent), When `sent_in_last_hour` and `last_requested_at` are read, Then 0 sent and the last request time is the newest creation time, so the cooldown applies and the cap does not (AC-29, AC-31) (type: edge; level: db).
  9. Given the cap of open requests, When one more is created, Then it is refused and no row is written (AC-16, W-7) (type: security; level: db).
  10. Given the table read as the owner, When inspected, Then no clear code is stored, only the hash (W-15) (type: security; level: db).

### U-web-settings-17: Request-code endpoint (R1)

- Layer: backend
- Contract: `POST /auth/request-code` (public, Origin check, `LimitGuard("signin")`) with `{username}`: limits first (client bucket, then the per-username cooldown and hourly cap), then the same `200 {maskedAddress, expiresAt, resendAfterSeconds}` and the same `Set-Cookie: __Host-login` (random id, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, Max-Age 600) for the configured and an unknown username; for the configured one a login request is created, the code from `CodeSource` is handed to the mailer; for an unknown one a dummy hash and the same code path timing are used and nothing is sent. A failed send gives the same 200, is logged and recorded as `mail_failed`, and still counts for the cooldown and the cap (ADR-0036). 429 with `Retry-After` for the cooldown and the hourly cap.
- Files: `backend/app/routers/auth.py`, `backend/app/auth/request_code.py`, `backend/tests/auth/test_request_code.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-12, U-web-settings-13, U-web-settings-16
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-oauth2-oidc, guardrail-pydantic
- Criteria:
  1. Given the configured username, When a code is requested, Then 200 with the masked address, `expiresAt` 10 minutes ahead, `resendAfterSeconds` 60, the cookie, and exactly one message in the fake mailer with the code of `FakeCodes` (AC-29) (type: happy; level: api).
  2. Given the configured and an unknown username, When requested, Then status, body shape and values (except per-request fields), header names, cookie attributes and cookie length are identical, and the mailer got no message for the unknown one (AC-30, W-2) (type: security; level: api).
  3. Given both cases, When the work done is counted (calls to hash and store, with the fake clock advancing a fixed step per call), Then the same number of steps run, so the timing class is the same (AC-30, W-2) (type: security; level: api).
  4. Given the mailer fails, When a code is requested, Then the answer equals the success answer, a `mail_failed` event exists, the failed send starts the cooldown (a second request within 60 s gets 429) and does not count towards the hourly cap, and nothing about the cause or the address is in the response or log (AC-29, AC-31, W-15) (type: security; level: api).
  5. Given a second request at 59 s and at 60 s after the first, whether the first send succeeded or failed, When requested, Then 429 with `Retry-After: 1`, then 200 and the earlier code no longer works (AC-5, AC-31) (type: edge; level: api).
  6. Given five sent codes in an hour (spaced 60 s) and a sixth request, When requested, Then the sixth gets 429 with `Retry-After` until the oldest sent code falls out of the hour (59 min 59 s still 429, 60 min 1 s 200) and no message is sent; Given instead five failed sends spaced 60 s, Then the sixth request is answered 200 and its message is sent, because the cap counts only sent codes (AC-5, AC-31, W-7) (type: edge; level: api). Superseded by D-16 and U-53: a failed send counts.
  7. Given a wrong or missing `Origin`, When requested, Then 403 and no login request row (AC-8, W-4) (type: security; level: api).
  8. Given a username of 65 characters, a control character or a non-string, When requested, Then 422 before any work and no log line contains it (W-15) (type: security; level: api).
  9. Given a refused request (429), When it happens, Then a `code_request_refused` event is recorded once per window (AC-20, AC-31) (type: security; level: db).
  10. Given the request-code route, When the inventory is read, Then it is `public` and carries the `signin` guard (AC-15, AC-16) (type: security; level: unit).

### U-web-settings-18: Verify-code endpoint and sign-in (R1)

- Layer: backend
- Contract: `POST /auth/verify-code` (public, Origin check, `LimitGuard("signin")`) with `{code, returnTo?}` and the `__Host-login` cookie: loads the request, checks it (U-16), and on `Ok` checks the web lock, creates the session (U-15), sets `__Host-session`, clears `__Host-login` and answers 204 with the validated return path in the body or a `Location`-free JSON `{returnTo}`; every failure answers one generic 400 whose body carries `attemptsLeft` only when the cookie names a live request, and clears `__Host-login` when the request is dead. Every outcome writes a security event.
- Files: `backend/app/routers/auth.py`, `backend/app/auth/verify_code.py`, `backend/tests/auth/test_verify_code.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-13, U-web-settings-15, U-web-settings-16
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-oauth2-oidc, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a requested code, When the right code is posted with the cookie, Then 204, a new `__Host-session`, `__Host-login` cleared, a `session_start` event, and `returnTo` is `/settings` (AC-7) (type: happy; level: api).
  2. Given a wrong code, an expired code (10:00), a used code, a code after 5 wrong attempts, a code from another browser's cookie, an old code after a new one, an unknown username's cookie and no cookie, When posted, Then each gets the same 400 body shape, no session exists, one test each (AC-3, AC-5, W-1) (type: security; level: api).
  3. Given wrong codes with a live request, When refused, Then the body has `attemptsLeft` 4, 3, 2, 1 in turn; with no cookie or a dead request the field is absent; the fifth wrong code clears `__Host-login` and a sixth attempt with the right code gets the generic 400 (AC-3, AC-5) (type: edge; level: api).
  4. Given two concurrent verify requests with the same right code and the same cookie, When both run, Then exactly one 204 and one 400, and exactly one session row exists (AC-3, W-1) (type: security; level: db).
  5. Given `returnTo` values `https://evil.example`, `//x`, `javascript:1`, When posted with the right code, Then the answer says `/settings` (AC-6, W-2) (type: security; level: api).
  6. Given `web_lock` set, When the right code is posted, Then no session and a `lock_refused` event, and the response status, body and headers are identical to the generic 400 of a wrong code with the request id as the only difference, with no explanation of the lock (AC-27, W-1) (type: security; level: db).
  7. Given a wrong or missing `Origin`, When posted, Then 403 and no attempt is counted (AC-8) (type: security; level: api).
  8. Given a refused code, When events are read, Then one `code_refused` event per client and window, with no code and no cookie value, and the canary code `424242` is in no log (AC-20, W-15) (type: security; level: db).
  9. Given a malformed body (`code` of 7 digits, letters, empty, an object), When posted, Then the same generic 400 and the attempt is not counted for a format error but the response is not distinguishable (AC-3, AC-15) (type: security; level: api).

### U-web-settings-19: CSRF, Origin, /api/session and logout (R1)

- Layer: backend
- Contract: the CSRF token is `HMAC(csrf_key, session_id)` compared in constant time (`app/auth/csrf.py`); `GET /api/session` (session, `Sec-Fetch-Site` same-origin) returns `{maskedAddress, csrfToken, idleExpiresAt, absoluteExpiresAt, noticeIntervalMinutes}`; `require_csrf` (marker `csrf`) needs `X-CSRF-Token` and `Origin` equal to the public origin (missing `Origin` or `Sec-Fetch-Site: cross-site` is refused with the one 403 body); `POST /auth/logout` (session, CSRF, Origin) answers 204, deletes the session and clears the cookie; a GET on a write route answers 405; no CORS.
- Files: `backend/app/auth/csrf.py`, `backend/app/routers/session.py`, `backend/app/routers/auth.py`, `backend/app/core/security.py`, `backend/tests/auth/test_csrf.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-15
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-oauth2-oidc
- Criteria:
  1. Given a session id, When the token is derived, Then it equals the HMAC, differs for another session id, and the comparison calls `hmac.compare_digest` (W-4) (type: security; level: unit).
  2. Given a same-origin `GET /api/session`, When answered, Then masked address, token, both expiry times and `noticeIntervalMinutes` from settings, and no username or full address (AC-15, W-15) (type: happy; level: api).
  3. Given `Sec-Fetch-Site: cross-site` on `GET /api/session`, When answered, Then 403 and no token (AC-8, W-4) (type: security; level: api).
  4. Given a write without the token, with a wrong token, and with a token of another session, When sent, Then 403 with the same body and nothing changes (AC-8, W-4) (type: security; level: api).
  5. Given a valid token with a wrong, missing or `null` `Origin`, or `Sec-Fetch-Site: cross-site`, When sent, Then 403 (AC-8, W-4) (type: security; level: api).
  6. Given a GET on a write route, When sent, Then 405 (AC-8) (type: security; level: api).
  7. Given a valid logout, When sent, Then 204, the session row is gone, the cookie is cleared and the old cookie then gets 401; Given a logout without the token, Then 403 and the session stays valid (AC-7, AC-8) (type: happy; level: db).
  8. Given two tabs of one session, When both use the token, Then both work (type: edge; level: api).
  9. Given a preflight `OPTIONS` or any response, When inspected, Then there is no `Access-Control-Allow-*` header; a CSRF refusal records `csrf_refused` once per client and window (AC-8, AC-20, W-4) (type: security; level: db).
  10. Given the route inventory, When read, Then every `POST` and `PUT` operation except the two public sign-in routes has the `session` and `csrf` markers; one without fails (AC-15) (type: security; level: unit).

### U-web-settings-20: Settings read: models, GET, RULES, field map, checked-in OpenAPI (R1)

- Layer: backend
- Contract: the read part of the settings API so the web can start next to the auth units. `Settings` `{values: {timeZone, quietStart, quietEnd, overviewAt, remindAt}, version, updatedAt, updatedVia}` (`HH:MM`, `additionalProperties: false`; at version 0 `updatedAt` and `updatedVia` are null, D-8), the schemas the write part will use (`SettingsUpdate`, `Problem422`, `Conflict409`) declared in the OpenAPI, `GET /api/settings` (session, `LimitGuard("api")`), `SettingsRepository.read()`, `schedule_policy.RULES` and the rule-to-field map `app/settings_fields.py` (pure), and `docs/api/openapi.json` regenerated. The write route is not in this unit.
- Files: `packages/schedule-policy/schedule_policy/policy.py`, `packages/schedule-policy/schedule_policy/__init__.py`, `backend/app/settings_repo.py`, `backend/app/settings_fields.py`, `backend/app/routers/settings.py`, `backend/tests/test_settings_read.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-09, U-web-settings-15
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a stored row, When `GET /api/settings`, Then the four values as `HH:MM`, version, `updatedAt` and `updatedVia`, and no actor field (AC-1, AC-15) (type: happy; level: api).
  2. Given no row, When `GET`, Then the defaults with `version: 0`, `updatedAt` and `updatedVia` null (AC-1, D-8) (type: edge; level: api).
  3. Given `RULES` exported by the package and the field map, When compared, Then every rule has a field and nothing extra; adding a rule to the package without a mapping fails the test (AC-10) (type: edge; level: unit).
  4. Given the rules `quiet_window_*`, `overview_in_quiet_hours`, `remind_in_quiet_hours`, `zone_unknown`, When mapped, Then start and end, overview, remind and zone fields as in the design (AC-10) (type: happy; level: unit).
  5. Given no session, an expired session and a locked web, When `GET`, Then 401 and nothing is read (AC-2, AC-27) (type: security; level: api).
  6. Given the exported OpenAPI, When read, Then it contains `Settings`, `SettingsUpdate`, `Problem422`, `Conflict409`, `additionalProperties: false` on each, the path `/api/settings` only with GET, and the web client types can be generated from it (AC-15) (type: happy; level: ci).
  7. Given the 31st request of one client in a window on a lowered limit and a `LimitGuard` fake that refuses, When `GET`, Then 429 (the route declares the guard) (AC-16) (type: edge; level: api).
  8. Given the package fixture `contract/settings_cases.json`, When the package tests run, Then they pass unchanged (AC-26) (type: happy; level: unit).

### U-web-settings-21: Settings write repository (R1)

- Layer: backend (database)
- Contract: `SettingsRepository.write(values, expected_version, username_hash) -> StoredSettings` as about 40 lines of SQLAlchemy Core: one `UPDATE ... WHERE version = :v RETURNING`, or `INSERT ... ON CONFLICT DO NOTHING` at version 0; `VersionConflict` carries the current row; the guard sets the channel and the audit trigger records the change in the same transaction. This unit extends `settings_repo.py` written by U-20.
- Files: `backend/app/settings_repo.py`, `backend/tests/db/test_settings_repo.py`, `backend/tests/db/test_contract_fixture.py`
- Depends on: U-web-settings-07, U-web-settings-09, U-web-settings-20
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pydantic
- Criteria:
  1. Given no row, When written at version 0, Then version 1 and the row exists; a second writer at version 0 gets `VersionConflict` (AC-9, AC-11) (type: happy; level: db).
  2. Given a write at version 1, When committed, Then version 2, exactly one `settings_change` record with `db_role` of the web role, channel `web` and `updated_by` of the form `web:<32 hex>` (AC-9, W-10) (type: happy; level: db).
  3. Given two sessions that read the same version and an explicit barrier, When both write, Then exactly one succeeds, the other gets `VersionConflict` with the current row, one audit record exists (AC-11, W-12) (type: edge; level: db).
  4. Given a stale version, When written, Then `VersionConflict` and nothing changes (AC-11) (type: error; level: db).
  5. Given the audit trigger function is replaced in the test by one that raises, When a write runs, Then the whole write is rolled back and the caller gets an error, not a success (AC-17) (type: security; level: db).
  6. Given a write that sets `version` to old plus 2, When executed through the role, Then 42501 (AC-17) (type: security; level: db).
  7. Given `contract/settings_cases.json`, When run through the repository, Then outcomes match the package and the agent (AC-26) (type: happy; level: db).
  8. Given a zone value `'; drop table settings.schedule; --`, When written, Then the statement is parameterised, the database CHECK refuses it and nothing changes (AC-10) (type: security; level: db).
  9. Given a failure path with the canary zone, When logs are captured, Then no record contains the canary (type: security; level: db).

### U-web-settings-22: Settings write route PUT (R1)

- Layer: backend
- Contract: `PUT /api/settings` (session, CSRF, Origin, `LimitGuard("api")`) takes `{values, version}`: format check, `schedule_policy.validate`, `repository.write`; 200 `Settings`, 409 `Conflict409` with the current `Settings`, 422 `problems: [{field, rule, value, example}]` mapped by U-20, 415 for a non-JSON body.
- Files: `backend/app/routers/settings.py`, `backend/tests/test_settings_write.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-19, U-web-settings-21
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given a valid `PUT` at the current version, When sent with session and token, Then 200 with the new `Settings` and the next version (AC-9) (type: happy; level: api).
  2. Given an overview inside the quiet hours, When `PUT`, Then 422 with `field: overviewAt`, the same rule text and example as Telegram, nothing stored (AC-10) (type: error; level: api).
  3. Given malformed times (`7pm`, `24:00`, `07:00:30`, a number), an unknown zone, `../etc` and an over-long zone, When `PUT`, Then 422 and nothing stored (AC-10) (type: security; level: api).
  4. Given an old version, When `PUT`, Then 409 with the current `Settings` and nothing stored (AC-11) (type: edge; level: api).
  5. Given an extra property in the body or a non-JSON content type, When `PUT`, Then 422 or 415 and nothing stored (AC-15) (type: security; level: api).
  6. Given a zone `<script>alert(1)</script>`, When `PUT`, Then 422 and the body carries it only as a JSON string (AC-14) (type: security; level: api).
  7. Given no session, a session without the token, a wrong `Origin` and a locked web, When `PUT`, Then 401 or 403 and nothing is written (AC-2, AC-8, AC-27) (type: security; level: api).
  8. Given a body over 8192 bytes, When the real guard is in place (U-24) or a stub guard refuses, Then the request never reaches validation (AC-16) (type: edge; level: api).
  9. Given a write whose audit trigger fails, When `PUT`, Then a generic 500 and nothing stored (AC-17) (type: security; level: db).
  10. Given the OpenAPI, When regenerated, Then `PUT /api/settings` is listed with the session and csrf markers and `/api/settings/reset` is absent (AC-15) (type: security; level: ci).

### U-web-settings-23: Places route (R1)

- Layer: backend
- Contract: `GET /api/places?q=` (session, `LimitGuard("api")`) returns up to 5 `{zone, label, utcOffsetMinutes}` and an optional suggestion from `schedule_policy.places.lookup` (same lookup and aliases as Telegram, ADR-0028); the live local time is computed in the browser. This unit makes the route inventory test exact (equals the allow-list).
- Files: `backend/app/routers/places.py`, `backend/tests/test_places_api.py`, `backend/tests/test_route_inventory.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-15
- Parallel: yes (with U-20 to U-22)
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given `q=New York`, When called, Then a hit for `America/New_York` with label and offset (C-7) (type: happy; level: api).
  2. Given `q=Paris`, When called, Then at most 5 labelled hits; `Nwe York` gives the suggestion `New York` (C-7) (type: edge; level: api).
  3. Given the aliases `NYC` and `Wien`, When called, Then the same results as the Telegram lookup (type: edge; level: api).
  4. Given nothing matches, When called, Then an empty list without error (type: edge; level: api).
  5. Given a 65-character `q`, a control character and an emoji, When called, Then 422 for the first two before matching, an empty or valid result for the emoji (C-7) (type: security; level: api).
  6. Given a typed canary place, When logs are captured, Then the query value is in no log line (W-15) (type: security; level: api).
  7. Given no session, When called, Then 401 (AC-2) (type: security; level: api).
  8. Given the response model, When checked, Then only `zone`, `label`, `utcOffsetMinutes` and `suggestion` exist, and the route inventory equals the allow-list exactly (AC-15) (type: security; level: unit).

### U-web-settings-24: In-process rate and body limits (R1; release gate)

- Layer: backend (pure module; mutation-gated)
- Contract: ADR-0034. Pure `app/limits.py` (`window_key(now) = floor(now / 60)`, fixed-window counter per client and bucket, bounded memory) and `app/clientaddr.py` (`client_key(peer, xff, trusted_cidrs, hops)`: the address the last trusted proxy appended; any other peer by its own address); the real `LimitGuard` replaces the no-op of U-05 for the buckets `signin` and `api`; body limit 8192 bytes (413, also chunked bodies without a length); a refused request records one `rate_limited` event per client and window. Limit values come from the settings of U-04 only.
- Files: `backend/app/limits.py`, `backend/app/clientaddr.py`, `backend/app/limit_guard.py`, `backend/app/middleware.py`, `backend/tests/test_limits.py`
- Depends on: U-web-settings-05, U-web-settings-13, U-web-settings-17, U-web-settings-18
- Parallel: yes (with U-19 to U-23)
- Guardrails: guardrail-fastapi, guardrail-python
- Criteria:
  1. Given 30 requests to `/auth/request-code` in one window, When the 31st arrives, Then 429 with an integer `Retry-After`; at 59.9 s still the same window, at 60.0 s a new window passes (AC-16, W-7) (type: edge; level: api).
  2. Given the `api` bucket on `/api/settings`, When one client exceeds it, Then 429 and the `signin` bucket is unaffected (AC-16) (type: edge; level: api).
  3. Given the limit is exceeded on the sign-in routes, When the database is read, Then no `login_request` row was written for the refused requests (AC-16, W-7) (type: security; level: db).
  4. Given `X-Forwarded-For: spoof, real` where the last trusted proxy appended `real`, When keyed, Then the key is `real`; a spoofed leftmost value never opens a fresh bucket; a peer outside the trusted CIDRs is keyed by its own address (W-7, W-17) (type: security; level: unit).
  5. Given a body of 8192 and 8193 bytes, and a chunked body over the limit, When sent to a write route, Then accepted, 413, 413, and the body is not parsed (AC-16) (type: edge; level: api).
  6. Given a flood from one client, When refused, Then exactly one `rate_limited` event exists for that client and window (AC-20, W-13) (type: security; level: db).
  7. Given limits lowered through settings (tests use 3), When the guard runs, Then they take effect; there is no second definition of a limit outside the settings (type: happy; level: unit).
  8. Given many distinct clients over many windows, When counters are held, Then windows older than two are dropped and the size stays bounded (W-7) (type: edge; level: unit).
  9. Given `window_key` at 59.9 s, 60.0 s and 60.1 s, When called, Then 0, 1 and 1 (type: edge; level: unit).
  10. Given the baseline mutation run of `limits.py` and `clientaddr.py`, When it finishes, Then the score is at least 85 % or every survivor is on the committed exclusion list (type: security; level: unit).

### U-web-settings-25: Walking skeleton at API level (M1)

- Layer: backend
- Contract: one test module that runs the whole first path in process, with fakes and a real database: request a code (read from `FakeMailer`), verify it, `GET /api/session`, `GET /api/settings`, `PUT /api/settings` once, `POST /auth/logout`. It exists to keep a working end-to-end path while later units add to it.
- Files: `backend/tests/test_walking_skeleton.py`
- Depends on: U-web-settings-18, U-web-settings-19, U-web-settings-22
- Parallel: no
- Guardrails: guardrail-pytest, guardrail-fastapi
- Criteria:
  1. Given a fresh database and fakes, When the allowed username signs in with the code from the fake mailer, Then `GET /api/session` shows the masked address and a token (AC-7) (type: happy; level: api).
  2. Given the session, When `GET /api/settings` then `PUT /api/settings` with a valid change and the token, Then version 0 becomes 1 and an audit record with channel web exists (AC-1, AC-9) (type: happy; level: db).
  3. Given the same path with a wrong code once, When retried with the right code, Then sign-in succeeds with the same request (attempt 2 of 5) (AC-3) (type: edge; level: api).
  4. Given the saved row, When read through the agent store, Then the agent sees the new values (AC-9, AC-26) (type: happy; level: db).
  5. Given logout, When the old cookie is used, Then 401 (AC-7) (type: security; level: api).
  6. Given the whole path, When logs are captured, Then no canary code, username, cookie or zone appears (W-15) (type: security; level: api).

### U-web-settings-26: Web notices in the agent (R1; release gate)

- Layer: agent
- Contract: at each run `WebNotice.run(now)` selects `settings_change` records whose `db_role` is not the agent role and whose version (as an integer) is above the cursor in `poll_state`, sends one Telegram notice per change (old and new values, change number, channel `web`, time; no username) with the buttons "Undo" and "Undo and lock web sign-in", records an own token per notice in the notice table (not the conversation row) through an injected token source, and advances the cursor. Delivery is at least once. Quiet hours never hold the notice.
- Files: `agents/mail-triage/app/usecases/web_notice.py`, `agents/mail-triage/app/db/pg_web_notice.py`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/app/core/settings_text.py`, `agents/mail-triage/tests/db/test_web_notice.py`
- Depends on: U-web-settings-06, U-web-settings-07
- Parallel: yes
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a web change to version 3, When the agent runs, Then exactly one notice with old values, new values, change number 3, channel web, time and both buttons (AC-13, W-11) (type: happy; level: agent).
  2. Given the notice was sent, When the agent runs again, Then no second notice (cursor advanced) (AC-13) (type: happy; level: agent).
  3. Given a change made through Telegram (agent role), When the agent runs, Then no web notice (AC-13) (type: edge; level: agent).
  4. Given web changes at versions 9, 10 and 11, When the agent runs, Then three notices in numeric order (10 after 9) (ADR-0033) (type: edge; level: agent).
  5. Given a failure injected between the send and the cursor update (a store fake that raises on `advance`), When the agent runs twice, Then the notice is sent twice (at least once), the cursor ends advanced and there is one token record per send; Given the outbox fails before the send, Then the cursor did not move and the notice is sent on the next run (AC-13) (type: error; level: agent).
  6. Given a pending Telegram dialogue (the conversation row), When a web notice is sent, Then the conversation row and its message are unchanged (AC-13, ADR-0033) (type: edge; level: agent).
  7. Given a `FakeClock` inside the quiet hours that the change itself just set, When the agent runs, Then the notice is sent (AC-13, ADR-0033) (type: edge; level: agent).
  8. Given a web row whose `updated_by` text claims the agent, When selected, Then the notice is still sent because selection uses the server-derived `db_role` (W-11) (type: security; level: db).
  9. Given the real agent role `mail_triage_runtime` (not the owner), When the use case writes the cursor and the token record, Then it works with the grants of U-07 (type: security; level: db).
  10. Given the new agent modules, When parsed with `ast`, Then they call none of `datetime.now`, `time.time`, `uuid4`, `random.*`, `secrets.*`; time and tokens are injected; and a failure path with canary zone and token leaves no canary in the logs (type: security; level: agent).

### U-web-settings-27: Notice buttons: Undo, Undo and lock, /web_unlock (R1; release gate)

- Layer: agent
- Contract: the callbacks `webundo:<token>` and `weblock:<token>` handled through the router: Undo restores the values as they were before the first web change the agent had not yet announced, guarded by the current version, with one audit record (via the agent role); "Undo and lock" first writes `web_auth.web_lock`, then undoes; the Telegram command `/web_unlock` (D-3) clears the lock; only the allowed user and chat.
- Files: `agents/mail-triage/app/usecases/web_notice_actions.py`, `agents/mail-triage/app/db/pg_web_lock.py`, `agents/mail-triage/app/usecases/dispatch.py`, `agents/mail-triage/app/core/settings_text.py`, `agents/mail-triage/tests/db/test_web_notice_actions.py`
- Depends on: U-web-settings-26
- Parallel: no
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given web changes 3, 4, 5 announced in three notices, When Undo of notice 5 is tapped, Then the values from before change 3 are restored with one audit record (AC-13, W-11) (type: happy; level: agent).
  2. Given the same burst, When Undo of notice 3 is tapped, Then the same result (AC-13) (type: edge; level: agent).
  3. Given Telegram changed the row after the burst, When Undo is tapped, Then nothing changes and the bot says it changed in the meantime (AC-13) (type: edge; level: agent).
  4. Given "Undo and lock", When tapped and the undo conflicts, Then `web_lock` is set anyway (AC-27, W-11) (type: security; level: db).
  5. Given "Undo and lock" tapped twice, When handled, Then one lock row and one undo (type: edge; level: db).
  6. Given `/web_unlock` from the allowed user, When sent, Then `web_lock` is cleared; from anyone else nothing happens and nothing is answered (AC-27) (type: security; level: agent).
  7. Given an expired or already used token, When tapped, Then the message is edited to "Expired" or "Already done" and nothing is written (type: edge; level: agent).
  8. Given a tap from another chat or user with a valid token, When handled, Then ignored (type: security; level: agent).
  9. Given the real agent role `mail_triage_runtime`, When the lock write and the undo run, Then both work with the grants of U-07 and no other `web_auth` table is touched (ADR-0033) (type: security; level: db).
  10. Given a failure path with canary zone and token, When logs are captured, Then no canary appears; and the new modules pass the same AST rule as U-26 (type: security; level: agent).

### U-web-settings-28: Web app shell, API client and session (R1)

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

### U-web-settings-29: UI primitives: Button, Field, Banner, TimeField, Layout (R1)

- Layer: web
- Contract: presentation components from the screens document, tokens only: `Button` (primary, secondary, ghost, danger; `loading`, `disabled`), `Field` (label, hint, error, ids by `useId`), `Banner` (danger, success, info; title, text, optional action), `TimeField` (native `input type=time` step 60, the 24-hour text beside it, stepped 15-minute select fallback), `Layout` (skip link, header with Sign out, `main`, focus ring from the token).
- Files: `apps/web/src/components/Button.tsx`, `apps/web/src/components/Field.tsx`, `apps/web/src/components/Banner.tsx`, `apps/web/src/components/TimeField.tsx`, `apps/web/src/components/Layout.tsx`
- Depends on: U-web-settings-01
- Parallel: yes (with the backend units)
- Guardrails: guardrail-react, guardrail-tailwind, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given `loading`, When rendered, Then the label changes ("Saving..."), `aria-disabled` is set and a second click calls the handler once in total (AC-23, W-12) (type: edge; level: component).
  2. Given a Field with hint and error, When rendered, Then the label is linked, hint and error are in `aria-describedby`, `aria-invalid` is set only when invalid, the error has `role="alert"` and a visible "!" mark (AC-23) (type: a11y; level: component).
  3. Given the TimeField with a stored `22:10`, When rendered, Then the value is shown unchanged with "= 22:10"; the select fallback offers 15-minute values plus the unrounded stored value (C-7) (type: edge; level: component).
  4. Given Banner kinds, When rendered, Then danger and conflict use `role="alert"`, success and info use `role="status"`, and each has a title element and a non-colour marker (AC-23) (type: a11y; level: component).
  5. Given a Banner re-rendered with the same props, When announced, Then the live region node is kept, not recreated (AC-23) (type: edge; level: component).
  6. Given Layout, When tabbed, Then the skip link is first and moves focus to `main` (AC-23) (type: a11y; level: component).
  7. Given every component in every state, When axe runs (contrast off in jsdom), Then no violation (AC-22) (type: a11y; level: component).
  8. Given `prefers-reduced-motion`, When set, Then the component sets no transition (AC-23) (type: a11y; level: component).

### U-web-settings-30: Login page: username step and code step (R1)

- Layer: web
- Contract: `/login` (public) with two steps on one page, from the screens document: step 1 heading "Sign in", label "Username" (`autocomplete=username`), button "Send me a code", fine print that a one-time code goes to the address on file and that no mail or calendar access is asked; step 2 heading "Enter your code", "We sent a code to `m***@example.com`. It is valid for 10 minutes.", numeric code field (`inputmode=numeric`, `autocomplete=one-time-code`, `maxlength=6`, spaces removed before sending), "Sign in", "Use another username", and the permanent hint "No code after a few minutes? Ask for a new one after the countdown, or check the mail setup." There is no "could not send" state and no provider button. Uses `POST /auth/request-code` and `POST /auth/verify-code`. The refusal states and resend are in U-31.
- Files: `apps/web/src/pages/LoginPage.tsx`, `apps/web/src/pages/UsernameStep.tsx`, `apps/web/src/pages/CodeStep.tsx`, `apps/web/src/pages/useSignIn.ts`, `apps/web/src/pages/LoginPage.test.tsx`
- Depends on: U-web-settings-28, U-web-settings-29, U-web-settings-17, U-web-settings-18
- Parallel: yes (with U-32)
- Guardrails: guardrail-react, guardrail-react-router, guardrail-tanstack-query, guardrail-a11y, guardrail-tailwind, guardrail-vitest-rtl
- Criteria:
  1. Given `/login`, When rendered, Then `h1` is first in `main`, the username field is the first control, and the fine print names what is asked and says no mail access is requested (AC-24) (type: happy; level: component).
  2. Given the button is pressed, When the request runs, Then it is disabled, reads "Sending...", has `aria-busy`, inputs are read-only and a polite status says "Sending your code." (AC-23) (type: a11y; level: component).
  3. Given the same 200 answer for a known and an unknown username, When step 2 appears, Then focus moves to the code field, the masked address from the answer is shown, and nothing in the page differs between the two cases (AC-24, AC-30) (type: security; level: component).
  4. Given a pasted code `123 456`, When submitted, Then `123456` is posted; letters are not accepted in the field (type: edge; level: component).
  5. Given a right code, When posted, Then the browser goes to `/settings`, whatever `returnTo` the page URL or the answer carries (AC-6) (type: happy; level: component).
  6. Given a 400 with `attemptsLeft: 3`, When shown, Then an inline `role="alert"` linked by `aria-describedby`: "That code is not right. You have 3 tries left." with "!" and border, `aria-invalid`, focus in the selected field (AC-3, AC-23) (type: error; level: component).
  7. Given a 400 without `attemptsLeft`, When shown, Then the same text without a number (AC-3) (type: edge; level: component).
  8. Given `?notice=expired` and any unknown notice such as `<script>`, When rendered, Then the first shows "Your session ended. Sign in again." with `role="status"`, the second renders nothing and nothing from the URL enters the DOM (AC-12 first half, AC-14) (type: security; level: component).
  9. Given the username, code and masked address, When the page is inspected, Then none is stored in `localStorage`, `sessionStorage` or a URL; the code field is cleared after step 2 ends (W-15) (type: security; level: component).
  10. Given axe on step 1, step 2 and the error states, When run, Then no violation; Tab reaches the controls in reading order (AC-23) (type: a11y; level: component).

### U-web-settings-31: Login page: resend, countdown and refusal states (R1)

- Layer: web
- Contract: the states of Screen 1 beyond U-30: "Send a new code" disabled for 60 seconds with visible countdown text ("You can ask for a new code in 52 seconds.", `aria-live=off`, with a separate hidden polite status for the start and the end only), "A new code was sent. The earlier code no longer works.", expired code banner with focus on "Send a new code", too many wrong tries (code field disabled until a new code), 429 cooldown from `Retry-After`, 429 hourly cap ("Try again in about 25 minutes."), web lock banner. The countdown uses an injected clock.
- Files: `apps/web/src/pages/ResendControl.tsx`, `apps/web/src/pages/useCountdown.ts`, `apps/web/src/pages/refusals.tsx`, `apps/web/src/pages/CodeStep.tsx`, `apps/web/src/pages/Refusals.test.tsx`
- Depends on: U-web-settings-30
- Parallel: no
- Guardrails: guardrail-react, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given a code sent at t, When the clock is at t+0, t+8 and t+60 s, Then the button is disabled with "in 60 seconds", "in 52 seconds", and enabled with "now"; the hidden polite status announced only at the start and the end (AC-31, AC-23) (type: a11y; level: component).
  2. Given "Send a new code" is pressed after the countdown, When the answer arrives, Then "A new code was sent. The earlier code no longer works.", the code field is cleared and the countdown restarts (AC-5) (type: happy; level: component).
  3. Given a 429 with `Retry-After: 41`, When shown, Then the info banner "Please wait before asking for another code. You can try again in 41 seconds." and the same countdown rule (AC-31) (type: error; level: component).
  4. Given a 429 with a long `Retry-After` from the hourly cap, When shown, Then the `role="alert"` banner "You have asked for too many codes this hour. Try again in about N minutes." with N rounded up, and the button stays disabled until then (AC-31, W-7) (type: error; level: component).
  5. Given the expired-code case (a 400 after more than 10 minutes by the injected clock), When shown, Then "This code has expired. Send yourself a new one." with focus on "Send a new code" and the code field cleared (AC-3) (type: error; level: component).
  6. Given `attemptsLeft: 0` or a dead request, When shown, Then "Too many wrong tries. This code no longer works. Send a new code." and the code field disabled until a new code is sent (AC-5) (type: error; level: component).
  7. Given the verify answer for a locked web (identical to the generic 400, U-18), When the page shows it, Then it shows exactly the generic refusal text and no mention of a lock; the page has no locked state (AC-27, W-1) (type: security; level: component).
  8. Given `prefers-reduced-motion`, When the countdown runs, Then the countdown is text only (AC-23) (type: a11y; level: component).
  9. Given axe on each state, When run, Then no violation (AC-22) (type: a11y; level: component).

### U-web-settings-32: Settings form with slots: load, validate, save (R1)

- Layer: web
- Contract: `/settings` with `useSettings()` (query `['settings']`) and a save mutation (`PUT` with `{values, version}`); fields in the order Time zone, Quiet hours (From, Until), Daily overview, Remind-me-later default, each with a hint; states loading, loaded, dirty, saving, validation error (422), save failed. The form composes three slot files that later units replace without editing the form: `ZoneField.tsx` (here a plain text input, rebuilt by U-33), `SaveFeedback.tsx` (here empty, rebuilt by U-34) and `ConflictLayer.tsx` (here empty, rebuilt by U-35). No Reset button in R1.
- Files: `apps/web/src/features/settings/SettingsPage.tsx`, `apps/web/src/features/settings/SettingsForm.tsx`, `apps/web/src/features/settings/useSettings.ts`, `apps/web/src/features/settings/fieldErrors.ts`, `apps/web/src/features/settings/ZoneField.tsx`, `apps/web/src/features/settings/SaveFeedback.tsx`, `apps/web/src/features/settings/ConflictLayer.tsx`
- Depends on: U-web-settings-22, U-web-settings-28, U-web-settings-29
- Parallel: yes (with U-30)
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-tailwind, guardrail-vitest-rtl
- Criteria:
  1. Given the loading state, When rendered, Then skeleton rows, the text "Loading your settings", `aria-busy`, and no Save button yet (AC-22) (type: happy; level: component).
  2. Given loaded settings, When rendered, Then the four fields in order, labelled "Time zone", "Quiet hours" (From, Until), "Daily overview", "Remind-me-later default", each with a hint linked by `aria-describedby` (AC-1, C-11) (type: happy; level: component).
  3. Given nothing changed, When viewed, Then Save is disabled; after an edit it is enabled (type: happy; level: component).
  4. Given Save is pressed, When the request runs, Then the label is "Saving...", Save is `aria-disabled`, inputs are read-only, a polite status says "Saving your settings." and exactly one `PUT` with `{values, version}` and the token is sent even on a double click (AC-9, AC-23, W-12) (type: edge; level: component).
  5. Given a 422 with problems for two fields, When shown, Then each message is next to its field with "!", `aria-invalid`, `aria-describedby` hint plus error, `role="alert"`, and focus moves to the first invalid field in DOM order (AC-10, AC-23) (type: error; level: component).
  6. Given a network error or 5xx, When shown, Then the danger banner "Could not save. Nothing was changed." with "Try again", typed values kept (type: error; level: component).
  7. Given the API returns `<img src=x onerror=alert(1)>` as zone, When rendered, Then it appears as text and no element is created (AC-14, W-5) (type: security; level: component).
  8. Given keyboard only, When the user tabs through, edits, submits invalid, fixes and saves, Then the whole flow works (AC-23) (type: a11y; level: component).
  9. Given the R1 build, When the DOM of the page is searched, Then there is no "Reset" control (R1 exposes no R2 surface) (type: security; level: component).
  10. Given axe on loading, loaded, dirty, saving, validation error and save-failed states, When run, Then no violation (AC-22) (type: a11y; level: component).

### U-web-settings-33: ZoneCombobox with live time (R1)

- Layer: web
- Contract: rebuild of `ZoneField.tsx` as an ARIA 1.2 combobox with list autocomplete: `GET /api/places?q=` (debounced), options "Bangkok, Thailand, UTC+7, 03:42 now" (with "(tomorrow)" or "(yesterday)" when the day differs), the stored value as "Currently: Europe/Amsterdam", a live local-time paragraph computed in the browser with `Intl.DateTimeFormat` from an injected clock; `UTC+7` and `GMT+7` accepted when the lookup supports them; keyboard model and announcements from the screens document.
- Files: `apps/web/src/features/settings/ZoneField.tsx`, `apps/web/src/features/settings/ZoneCombobox.tsx`, `apps/web/src/features/settings/useZoneSearch.ts`, `apps/web/src/features/settings/liveTime.ts`, `apps/web/src/features/settings/ZoneCombobox.test.tsx`
- Depends on: U-web-settings-23, U-web-settings-32
- Parallel: no
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the combobox, When rendered, Then `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete="list"` and `aria-activedescendant` are correct through open and close (AC-23, C-7) (type: a11y; level: component).
  2. Given the user types "bang", When the search resolves, Then options read "Bangkok, Thailand, UTC+7, 03:42 now" and a hidden polite region says "3 places found" (C-7) (type: happy; level: component).
  3. Given the keyboard, When Down, Up, Enter, Escape, a second Escape, Tab, Home and End are used, Then the active option moves with focus staying in the input, Enter selects, Escape closes, the second Escape restores the saved value, Tab accepts nothing unselected (AC-23) (type: a11y; level: component).
  4. Given a chosen zone and a fake clock, When the paragraph updates, Then "In Amsterdam it is 21:42 right now." appears after a 300 ms pause and on selection, inside an `aria-live="polite"` region, correct on both sides of a clock change (AC-28, C-7) (type: happy; level: component).
  5. Given text with no match, When the search returns empty, Then the hint "Nothing found for 'Phuket'. Try the nearest bigger city, or the country." (not `role="alert"`), and an API suggestion is offered (C-7) (type: error; level: component).
  6. Given the field loses focus with unselected text, When blurred, Then the saved value returns; it is never left empty (type: edge; level: component).
  7. Given a place label with markup from the API, When shown, Then it is text only (AC-14) (type: security; level: component).
  8. Given two searches where the first answers late, When both resolve, Then only the latest result is shown (type: edge; level: component).
  9. Given the typed query, When the page is inspected, Then it is in no URL, storage or log (W-15) (type: security; level: component).
  10. Given axe on closed, open, empty and no-result states, When run, Then no violation (AC-22) (type: a11y; level: component).

### U-web-settings-34: Save feedback: last-change line, saved banner, zone preview (R1)

- Layer: web
- Contract: rebuild of `SaveFeedback.tsx`: `LastChangeLine` ("Last changed from Telegram at 14:02" with `<time datetime>`, from the web, or "Using the default settings." at version 0); the saved banner with what is true now and `noticeIntervalMinutes` from `GET /api/session` (D-1); the permanent sentence under the times and the zone hint; the zone-change preview computed from the form values and the injected clock. The zone is the first field (U-32).
- Files: `apps/web/src/features/settings/SaveFeedback.tsx`, `apps/web/src/features/settings/LastChangeLine.tsx`, `apps/web/src/features/settings/ZonePreview.tsx`, `apps/web/src/features/settings/zoneMath.ts`, `apps/web/src/features/settings/SaveFeedback.test.tsx`
- Depends on: U-web-settings-32, U-web-settings-33
- Parallel: yes (with U-35)
- Guardrails: guardrail-react, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the last change from Telegram at 14:02 Amsterdam time, When shown, Then "Last changed from Telegram at 14:02" with `<time datetime>`; from the web "from the web"; at version 0 "Using the default settings." (AC-1, C-6) (type: happy; level: component).
  2. Given a successful save at 21:42 in Bangkok and `noticeIntervalMinutes` 5, When the banner shows, Then "Saved at 21:42. Quiet hours are 23:00 to 07:00 (Bangkok time). A message with an Undo button follows on Telegram within about 5 minutes." with `role="status"`, focus staying on Save, and the line now says "from the web" (AC-28, AC-13) (type: happy; level: component).
  3. Given `noticeIntervalMinutes` 1 and 5, When rendered, Then "about 1 minute" and "about 5 minutes" (type: edge; level: unit).
  4. Given the zone changed from Europe/Amsterdam to Asia/Bangkok before saving, When previewed, Then "Quiet hours will now be 22:00 to 07:00 Bangkok time (16:00 to 01:00 Amsterdam time)." and the form's clock times are unchanged (AC-28) (type: happy; level: component).
  5. Given the zone changed back to the saved one, When previewed, Then the preview disappears (type: edge; level: component).
  6. Given Asia/Kolkata, a day boundary and a date inside a clock change, When previewed, Then converted times are correct for the injected date (AC-28) (type: edge; level: unit).
  7. Given the page, When rendered, Then the zone is first in DOM and tab order, the sentence "Quiet hours, the overview and reminders follow this time zone." and the hint "The times below are local times in this zone." are present (AC-28) (type: happy; level: component).
  8. Given the preview and the banner, When read by a screen reader, Then neither is `role="alert"` and the success banner is the only live announcement of the save (AC-23) (type: a11y; level: component).

### U-web-settings-35: Conflict handling: Use mine and Keep Telegram's (R1)

- Layer: web
- Contract: rebuild of `ConflictLayer.tsx`: on 409 the form takes the returned `Settings`, shows the info banner (`role="alert"`, focus moves to it, "Nothing is saved until you press Save again.") and marks every field Marco had edited with his own value and two toggle buttons "Use mine" and "Keep Telegram's"; nothing is saved until Save is pressed again with the new version.
- Files: `apps/web/src/features/settings/ConflictLayer.tsx`, `apps/web/src/features/settings/ConflictBanner.tsx`, `apps/web/src/features/settings/useConflict.ts`, `apps/web/src/features/settings/Conflict.test.tsx`
- Depends on: U-web-settings-32
- Parallel: yes (with U-33, U-34)
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the page at version 1 and a 409 with version 2, When shown, Then the banner "Settings changed in Telegram at 14:02 (Amsterdam time). I loaded the new values." has `role="alert"` and focus, and the fields show the new values (AC-11) (type: happy; level: component).
  2. Given Marco edited quiet start to 22:30 and Telegram has 23:00, When shown, Then that field says "You typed 22:30, Telegram now has 23:00" with "Use mine" and "Keep Telegram's"; unedited fields have no mark (AC-28) (type: happy; level: component).
  3. Given "Use mine", When pressed, Then the field holds 22:30 again as an unsaved edit (AC-28) (type: happy; level: component).
  4. Given "Keep Telegram's", When pressed, Then the mark is gone and the field holds 23:00 (AC-28) (type: happy; level: component).
  5. Given the conflict and no button or Save pressed, When time passes, Then nothing is sent; Save afterwards sends the new version (AC-11) (type: edge; level: component).
  6. Given the other change came from the web in another tab, When shown, Then the banner says "from the web" (type: edge; level: component).
  7. Given a second 409 while resolving, When it arrives, Then the banner and marks are recomputed against the newest values (type: edge; level: component).
  8. Given the buttons, When read by a screen reader, Then each is named with its field ("Use mine for Quiet hours") and axe finds no violation (AC-23) (type: a11y; level: component).

### U-web-settings-36: Accessibility and responsive states: Playwright ui-states (R1; release gate)

- Layer: web
- Contract: a Playwright project `ui-states` with a stubbed API (`route.fulfill`, no backend) that renders every state of the login page (step 1, sending, step 2, wrong code, expired code, too many tries, cooldown, hourly cap, session expired), the settings page (loading, loaded, dirty, saving, saved, validation error, save failed, conflict, session expired) and the not-found and refused (403) pages, at 320, 375, 768 and 1280 px, in light and dark, and at 200 % text size. This is the only place for pixel, contrast and overflow checks (AC-22, AC-23).
- Files: `apps/web/e2e/ui-states.spec.ts`, `apps/web/e2e/support/stubs.ts`, `apps/web/playwright.config.ts`
- Depends on: U-web-settings-30, U-web-settings-31, U-web-settings-32, U-web-settings-33, U-web-settings-34, U-web-settings-35
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y
- Criteria:
  1. Given every state at every viewport, When measured, Then `scrollWidth` is at most `clientWidth` (AC-22) (type: a11y; level: playwright).
  2. Given every state at every viewport in light and dark, When axe runs with contrast on, Then no violation (AC-22) (type: a11y; level: playwright).
  3. Given text at 200 % size, When rendered, Then nothing is clipped or overlaps, and the buttons stack with the primary one first at 320 px (AC-22) (type: edge; level: playwright).
  4. Given the keyboard only, When the stubbed login-to-saved flow runs, Then every step is reachable, and on submit with an invalid field focus lands on the first invalid field (AC-23) (type: a11y; level: playwright).
  5. Given each interactive element, When focused, Then the outline has a computed non-zero width and the token colour (AC-23) (type: a11y; level: playwright).
  6. Given every target, When measured, Then at least 24 px on any viewport and at least 44 px on the touch viewports, with 8 px between neighbours (AC-23) (type: a11y; level: playwright).
  7. Given a slow stubbed save, When pending, Then Save is disabled and a second click sends no second request (AC-23, W-12) (type: edge; level: playwright).
  8. Given `prefers-reduced-motion: reduce`, When rendered, Then computed animation and transition durations are 0 (AC-23) (type: a11y; level: playwright).
  9. Given the `ui-states` project, When run in CI, Then it needs no backend and runs in the `web` job (type: happy; level: ci).

### U-web-settings-37: Prod-like TLS edge and nginx exact routes (R1)

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

### U-web-settings-38: Prod-like mail catcher with STARTTLS and the api service (R1)

- Layer: infra
- Contract: the mail catcher (existing `mail` service, port 8025) accepts SMTP with STARTTLS and a certificate from the internal CA in the prod-like profile; the `api` service gets its settings by reference (username, address, SMTP host `mail`, port, send-only credential of the catcher, keys, public origin of the edge, raised e2e limits) and trusts the internal CA through `SSL_CERT_FILE` (compose only; no CA or verify setting in the Helm values); a test helper `apps/web/e2e/support/mailbox.ts` reads the newest message and extracts the code from the catcher's HTTP interface.
- Files: `compose.yaml`, `deploy/prod-like/mail-tls.sh`, `apps/web/e2e/support/mailbox.ts`
- Depends on: U-web-settings-12, U-web-settings-37
- Parallel: no
- Guardrails: guardrail-compose, guardrail-docker, guardrail-tls-certificates
- Criteria:
  1. Given a code request through the edge, When the api sends, Then the catcher holds one message, received over STARTTLS with the CA-signed certificate (AC-29, W-14) (type: happy; level: image).
  2. Given the catcher is told to refuse STARTTLS, When a code is requested, Then no message arrives, the api logs the class only, and the response is still the success answer (AC-29, W-14) (type: security; level: image).
  3. Given the helper, When it reads the newest message, Then it returns the six-digit code and the subject has no code (AC-29) (type: happy; level: image).
  4. Given the api service environment, When rendered, Then every sensitive value is a reference, nothing is literal, and the raised limits exist only in the prod-like profile (AC-16) (type: security; level: ci).
  5. Given the default and `dev` profiles, When rendered, Then the raised e2e limits are not set there (type: security; level: ci).
  6. Given the api image start-up with a missing SMTP setting in the environment, When `up --wait` runs, Then the api does not become healthy and the log names the field (AC-4) (type: error; level: image).

### U-web-settings-39: Prod-like TLS database (R1)

- Layer: infra
- Contract: PostgreSQL in the prod-like profile serves TLS with a certificate from the internal CA for the host name `db`; the web role's `DATABASE_URL` uses the asyncpg `ssl` setting with `verify-full` (not libpq `sslmode`) and the CA file; the migrate service in the profile runs with the web role password (U-08).
- Files: `compose.yaml`, `deploy/prod-like/db-tls.sh`, `backend/tests/e2e/test_db_tls.py`
- Depends on: U-web-settings-08, U-web-settings-09, U-web-settings-37
- Parallel: yes (with U-38)
- Guardrails: guardrail-compose, guardrail-docker, guardrail-tls-certificates, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the stack, When the api connects as the web role, Then the connection is TLS and `/readyz` is 200 (W-8, W-9) (type: happy; level: image).
  2. Given a connection by an alias that is not in the certificate, When the engine of U-09 connects, Then it is rejected with a host name error (W-9) (type: security; level: image).
  3. Given a CA file that did not sign the server certificate, When the engine connects, Then it is rejected (W-9) (type: security; level: image).
  4. Given a plain, non-TLS connection attempt as the web role, When made to the server, Then the server refuses it (W-9) (type: security; level: image).
  5. Given the migrate service in the profile, When it runs, Then both roles exist and no runtime container uses the owner credentials (AC-17) (type: security; level: image).
  6. Given `docker compose config`, When searched, Then no literal password or URL with a password (type: security; level: ci).

### U-web-settings-40: Chart: local ingress, TLS and exposed paths (R1)

- Layer: infra
- Contract: the `app` chart ingress is local only (ADR-0037): no public host in any values file, a private address and a local host name from per-environment values; routes exactly `/api` and `/auth` to `api` and `/` to `web`; HTTP to HTTPS redirect; TLS 1.2 minimum; a certificate from a private CA through the issuer in values; `ingress.hsts` actually used (`max-age=31536000`, no `includeSubDomains`, no `preload`). Controller-specific parts (8 KB body cap, TLS minimum, log format with `$uri`) come from per-environment values (hosting is an open point).
- Files: `deploy/charts/app/templates/ingress.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/envs/local/values.yaml`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-kubernetes, guardrail-helm, guardrail-tls-certificates
- Criteria:
  1. Given the rendered ingress, When read, Then paths are exactly `/api` and `/auth` to the api service and `/` to web, and no rule routes `/docs`, `/openapi.json`, `/healthz`, `/readyz` or `/metrics` (AC-19, W-6) (type: security; level: chart).
  2. Given the rendered ingress with `tls.enabled`, When read, Then a `tls` block with the host and secret, an HTTP to HTTPS redirect, the issuer annotation from values and the HSTS setting from `ingress.hsts` without `includeSubDomains` and `preload` (AC-18, W-9) (type: security; level: chart).
  3. Given a values file with `tls.enabled: false`, `hsts: false`, or a host that is a public-looking name outside the configured local suffix, When `helm lint --strict` runs, Then it fails (AC-18, W-17) (type: error; level: chart).
  4. Given the local environment values (kind), When rendered, Then the 8 KB body cap, TLS 1.2 minimum and a log format without the query string are set through values; the chart default has no controller-specific annotation (AC-16, W-9) (type: security; level: chart).
  5. Given any values file in `deploy/`, When searched, Then there is no `LoadBalancer` service for api or web, no `nodePort` and no `externalIPs` (ADR-0037, W-17) (type: security; level: chart).
  6. Given the rendered output, When checked with kubeconform and kube-linter, Then both pass (type: happy; level: chart).

### U-web-settings-41: Chart: NetworkPolicy, one replica, secrets and SMTP egress (R1; release gate)

- Layer: infra
- Contract: ADR-0034, ADR-0029, design section "Deployment". `api.replicas` is 1 (schema maximum 1); `api` and `web` ingress NetworkPolicy accepts from one peer (namespace selector and pod selector in one `from` item) selecting the ingress controller; `api` egress to the database, DNS and the SMTP host and port from values only (no TCP 443 rule, no identity-provider egress); no `web-to-api` rule; the api reads database URL, code-hash key, CSRF key, username-hash key from the Secret `<release>-api` and the SMTP credential from a second Secret (both SealedSecrets created by the operator, README steps); username, address, SMTP host and port, public origin and notice interval are plain values. An optional certificate-expiry `PrometheusRule` 14 days ahead, off by default (D-7; a gate for production).
- Files: `deploy/charts/app/templates/networkpolicy.yaml`, `deploy/charts/app/templates/workloads.yaml`, `deploy/charts/app/templates/certalert.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/charts/app/README.md`
- Depends on: U-web-settings-08, U-web-settings-40
- Parallel: no
- Guardrails: guardrail-kubernetes, guardrail-helm, guardrail-tls-certificates
- Criteria:
  1. Given the rendered api Deployment, When read, Then `replicas: 1`; a values file with 2 fails the schema (ADR-0034, W-7) (type: security; level: chart).
  2. Given the rendered NetworkPolicy, When read, Then ingress to `api` and `web` has exactly one `from` item with a namespace selector and a pod selector together, and no empty selector (W-9, W-17) (type: security; level: chart).
  3. Given the render, When searched, Then there is no `web-to-api` rule and no policy that admits every namespace (W-17) (type: security; level: chart).
  4. Given the api egress, When read, Then only the database, DNS (UDP and TCP 53) and the SMTP host and port from values; no TCP 443 rule and no `0.0.0.0/0` (W-9, W-16) (type: security; level: chart).
  5. Given the api container env, When read, Then database URL, the three keys and the SMTP credential come from `secretKeyRef` and appear in no values file, ConfigMap or template literal (ADR-0029, W-16) (type: security; level: chart).
  6. Given the chart and the README, When searched for `sslmode=disable`, `verify-none`, `insecure` and `SSL_CERT_FILE`, Then no hit; the README documents the asyncpg `ssl` `verify-full` setting for the database URL (W-8, W-9) (type: security; level: chart).
  7. Given `certAlert.enabled=true`, When rendered, Then a `PrometheusRule` with a 14-day expiry condition; when false nothing is rendered (D-7, W-9) (type: happy; level: chart).
  8. Given the README, When checked, Then sealing uses standard input and no `--from-literal=` for secret keys, and the new keys are listed (ADR-0029) (type: security; level: chart).
  9. Given `helm lint --strict`, kubeconform and kube-linter for the `app` chart, When run, Then they pass (readiness `/readyz`, liveness `/healthz`, non-root, read-only root file system) (type: happy; level: chart).

### U-web-settings-42: One prod-like CI job, setup project and smoke test (R1; M2)

- Layer: infra
- Contract: one CI job `prod-like` replaces the separate `e2e` and `runtime-role` jobs, in this order: start the database and the mail catcher; run the migrate service with `docker compose run --rm`; `up --wait`; the database and role checks (the 19 forbidden statements of the agent role plus the web role's); the Playwright `setup` project (signs in once with the code read from the catcher and saves the storage state); `smoke.spec.ts` (open `/settings`, save once); then, in U-43, `journey`; then the log-grep script over the logs of `api`, `web`, edge, `db` and `migrate`. The agent is not in the prod-like stack (it needs real Gmail, Telegram and Anthropic credentials).
- Files: `.github/workflows/ci.yml`, `apps/web/e2e/setup.ts`, `apps/web/e2e/smoke.spec.ts`, `scripts/prodlike-checks.sh`, `agents/mail-triage/tests/e2e/test_web_role.py`
- Depends on: U-web-settings-30, U-web-settings-32, U-web-settings-37, U-web-settings-38, U-web-settings-39
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-docker, guardrail-compose
- Criteria:
  1. Given `ci.yml`, When read, Then one job runs the stated sequence and the old `e2e` and `runtime-role` jobs are gone with their checks kept (type: happy; level: ci).
  2. Given the `setup` project, When it runs, Then the allowed user is signed in with the code from the catcher and the storage state is reused (AC-3, AC-7) (type: happy; level: playwright).
  3. Given the smoke test, When it runs at 375 and 1280 px over real HTTPS, Then `/settings` shows the seeded values, a valid change is saved and a reload shows it (AC-1, AC-9) (type: happy; level: playwright).
  4. Given the web role in the running stack, When it reads `mail_item`, `oauth_token` or `settings_change`, runs DDL, or writes a bad `updated_by`, Then SQLSTATE 42501 each (AC-17, W-8) (type: security; level: ci).
  5. Given a successful sign-in and failure paths (a wrong code, a request for an unknown canary username, a refused STARTTLS, a rejected zone), When the logs of `api`, `web`, edge, `db` and `migrate` are grepped, Then none contains the code, `code=`, the canary username, the canary zone, the SMTP password or a cookie value (AC-20, W-15) (type: security; level: ci).
  6. Given the sequence, When the migrate step fails, Then the job fails before `up --wait` and uploads the logs (type: error; level: ci).
  7. Given a failing run, When it ends, Then the Playwright report and the logs are uploaded and the stack is brought down (type: happy; level: ci).

### U-web-settings-43: Journey over the prod-like stack (R1; release gate)

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
  7. Given `/docs`, `/redoc`, `/openapi.json`, `/healthz`, `/readyz`, `/metrics`, `/api/docs`, `/api/openapi.json`, `/api/readyz` and `/api/settings/reset` through the edge, When requested, Then 404 each; plain HTTP redirects with HSTS (AC-18, AC-19, R1 has no R2 surface) (type: security; level: playwright).
  8. Given a zone change, When saved, Then the preview, the saved banner with the real notice interval and the last-change line show (AC-28) (type: happy; level: playwright).
  9. Given the sign-in and settings pages at 375 and 1280 px over HTTPS with the real backend, When axe runs, Then no violation (AC-22) (type: a11y; level: playwright).
  10. Given a locked web (the lock row inserted by owner SQL), When the signed-in user calls the API and when a new code is requested and verified, Then 401, and the verify answer is identical in status and body (request id aside) to the answer for a wrong code (AC-27) (type: security; level: playwright).

### U-web-settings-44: Mutation workflow wiring for the pure security modules (R1; release gate)

- Layer: infra
- Contract: ADR-0030 item 4 extended to the backend: `backend/cosmic-ray.toml` lists every module that carries the marker `# pure module (mutation-gated)` (U-10, U-11, U-24: `code_hash.py`, `mask.py`, `digest.py`, `return_to.py`, `code_rules.py`, `expiry.py`, `limits.py`, `clientaddr.py`), with annotations excluded; `.github/workflows/mutation.yml` gets a `backend` job like the others (schedule and manual start, fails below 85 %). The baseline gate already ran per unit; this unit only wires the schedule.
- Files: `backend/cosmic-ray.toml`, `.github/workflows/mutation.yml`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/tests/test_mutation_config.py`
- Depends on: U-web-settings-10, U-web-settings-11, U-web-settings-24
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given `mutation.yml`, When read, Then a `backend` job triggers on `schedule` and `workflow_dispatch`, runs cosmic-ray and fails when more than 15 % of mutants survive (ADR-0030) (type: happy; level: ci).
  2. Given `cosmic-ray.toml`, When compared with the modules that carry the marker, Then the lists are equal; a new marked module without an entry, or an entry for a module that is gone, fails (the config cannot go stale) (type: security; level: unit).
  3. Given the config, When read, Then annotations are excluded from mutation (type: happy; level: unit).
  4. Given each listed module, When its imports are read, Then none imports FastAPI, SQLAlchemy or the network (type: edge; level: unit).
  5. Given the first manual run, When it finishes, Then its score and survivors are recorded under "Changes made during the build" with the committed exclusion lists, each survivor killed or listed with a reason (type: happy; level: ci).

### U-web-settings-45: Reset to defaults: backend (R2)

- Layer: backend
- Contract: `POST /api/settings/reset` (session, CSRF, Origin, `LimitGuard("api")`) with `{version}` writes `DEFAULT_POLICY` through the same repository and validation as `PUT`; 200 `Settings`, 409 on an old version. The allow-list and the route inventory gain the path in this unit only.
- Files: `backend/app/routers/settings.py`, `backend/tests/test_settings_reset_api.py`, `backend/tests/test_route_inventory.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-22
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given a changed row, When reset at the current version, Then the defaults including the time zone are stored through the repository and 200 with the new `Settings` (AC-25) (type: happy; level: db).
  2. Given the reset, When the audit is read, Then one record with channel web and `updated_by` of the form `web:<32 hex>` exists (AC-25, W-10) (type: security; level: db).
  3. Given an old version, When reset, Then 409 with the current `Settings` and nothing changes (AC-11) (type: edge; level: api).
  4. Given no token, a wrong `Origin` or no session, When reset, Then 403 or 401 and nothing changes (AC-8, AC-25) (type: security; level: api).
  5. Given a GET on the route, When sent, Then 405 (AC-8) (type: security; level: api).
  6. Given the reset, When the agent next runs, Then a web notice follows like any web change (AC-13) (type: happy; level: agent).
  7. Given the route inventory, When read, Then the path is on the allow-list with the session and csrf markers (AC-15) (type: security; level: unit).

### U-web-settings-46: Reset to defaults: web (R2)

- Layer: web
- Contract: the secondary button "Reset to defaults", kept apart from Save, opens `ConfirmDialog` (native `<dialog>` with `showModal`) that names the values including the time zone; the destructive button reads "Replace my settings with defaults", initial focus is "Keep my settings"; on confirm the page calls `POST /api/settings/reset`, shows the saving state and the banner "Defaults restored. The Undo button is in the Telegram message." The form renders the button through a slot file `ResetSlot.tsx` that U-32 left empty.
- Files: `apps/web/src/components/ConfirmDialog.tsx`, `apps/web/src/features/settings/ResetSlot.tsx`, `apps/web/src/features/settings/Reset.test.tsx`, `apps/web/e2e/ui-states.spec.ts`
- Depends on: U-web-settings-32, U-web-settings-45
- Parallel: no
- Guardrails: guardrail-react, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl, guardrail-playwright
- Criteria:
  1. Given the dialog opens, When rendered, Then it lists "Time zone Europe/Amsterdam, quiet hours 23:00 to 07:00, daily overview 18:00, reminders 09:00", says the time zone is reset too, and initial focus is "Keep my settings" (AC-25) (type: a11y; level: component).
  2. Given the dialog, When Escape or "Keep my settings" is used, Then it closes, nothing is sent and focus returns to the Reset button (AC-25) (type: happy; level: component).
  3. Given the dialog open, When Tab is pressed repeatedly, Then focus stays inside and the page behind is inert (AC-23) (type: a11y; level: component).
  4. Given confirm, When pressed, Then Save and Reset are disabled, one `POST /api/settings/reset` with the version is sent, and the banner shows (AC-25) (type: happy; level: component).
  5. Given a 409 on reset, When received, Then the conflict banner of U-35 shows and nothing is replaced (AC-11) (type: edge; level: component).
  6. Given the two dialog buttons in greyscale, When rendered, Then the destructive one differs by label, border and weight, not by colour alone (ADR-0035) (type: a11y; level: playwright).
  7. Given the dialog at 320, 375, 768 and 1280 px and 200 % text, When rendered, Then no horizontal scroll and axe finds no violation; the Reset button stacks below Save at 320 px (AC-22) (type: a11y; level: playwright).

### U-web-settings-47: Typed values kept across session expiry (R2)

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

### U-web-settings-48: Telegram alert after 5 wrong or expired codes (R1 since ADR-0039)

- Layer: agent
- Contract: the agent role gains `SELECT` on `web_auth.security_event` (grants.sql); at each run it counts `code_refused` events in the last 10 minutes; at 5 or more it sends one notice (count, time; no code, no username), at most one per 10 minutes. Other kinds (`code_request_refused`, `rate_limited`, `csrf_refused`, `mail_failed`) never count and never alert.
- Files: `agents/mail-triage/app/usecases/code_alert.py`, `agents/mail-triage/app/db/pg_security_events.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/tests/db/test_code_alert.py`
- Depends on: U-web-settings-13, U-web-settings-26
- Parallel: yes
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given 5 `code_refused` events within 10 minutes (`FakeClock`), When the agent runs, Then one notice with the count and time and no code or username (AC-20 second half, W-13) (type: happy; level: agent).
  2. Given 4 events, and 5 events spread over 10 minutes 1 second, When the agent runs, Then no notice (AC-20) (type: edge; level: agent).
  3. Given 50 `rate_limited`, `csrf_refused` and `mail_failed` events, When the agent runs, Then no notice (AC-20) (type: security; level: agent).
  4. Given a notice was sent, When the agent runs again within 10 minutes with more events, Then no second notice; after 10 minutes a new one may follow (type: edge; level: agent).
  5. Given the real agent role, When it selects `security_event`, Then it works; when it inserts, updates or deletes there, or touches `session` or `login_request`, Then 42501 (type: security; level: db).
  6. Given logs and the notice text, When captured with canary values, Then no digest, username or code appears (W-13, W-15) (type: security; level: agent).

### U-web-settings-49: Audit retention purge in the migrate job (R1 since 2026-11-13)

- Layer: backend (database; agent image)
- Contract: `python -m app purge` runs under the owner role as a step of the migrate job, after migrate and grants (not a CronJob, not a runtime role): it deletes `settings.settings_change` rows older than one year and `web_auth.security_event` rows older than 90 days (Marco, 2026-11-13) (injected clock) and expired `login_request` and `session` rows. `settings_change` stays append-only for the runtime roles through grants; the owner purge is the one documented delete path. The migrate command runs the step, so the Job and the compose service need no change.
- Files: `agents/mail-triage/app/db/purge.py`, `agents/mail-triage/app/db/migrate.py`, `agents/mail-triage/app/__main__.py`, `agents/mail-triage/tests/db/test_purge.py`
- Depends on: U-web-settings-07, U-web-settings-08
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-python, guardrail-helm, guardrail-kubernetes
- Criteria:
  1. Given audit records 366 days and 364 days old (`FakeClock`), When the purge runs, Then only the older one is removed (AC-21) (type: happy; level: db).
  2. Given a record exactly 365 days old, When the purge runs, Then the boundary follows one stated rule, tested on both sides (AC-21) (type: edge; level: db).
  3. Given `security_event` rows older than 90 days, and expired `login_request` and `session` rows, When the purge runs, Then they are removed and live rows stay (AC-21, W-13) (type: happy; level: db).
  4. Given the agent role and the web role, When they delete from `settings_change` or truncate it, Then 42501 still (AC-17) (type: security; level: db).
  5. Given the migrate job, When it runs, Then the order is migrate, grants, purge, and a failing purge makes the job exit non-zero naming the step (AC-21) (type: error; level: db).
  6. Given the rendered worker chart, When searched, Then there is no `CronJob` and no workload with the owner secret other than the migrate Job (AC-21, W-13) (type: security; level: chart).
  7. Given the purge, When logs are captured, Then only the counts of removed rows are logged (type: security; level: db).
  8. Given the purge run twice, When repeated, Then the second removes nothing (type: edge; level: db).

### U-web-settings-50: Decoy login requests for unknown usernames (R1; release gate; ADR-0038)

- Layer: backend
- Contract: a request for an unknown username creates a decoy login request (same row, `__Host-login` cookie, expiry, attempt counter and cooldown as a real one; no code is sent and no matching hash is stored); verify-code counts attempts and answers `attemptsLeft` for a decoy exactly as for a real request; a wrong-format code is handled the same way for both.
- Files: `backend/app/auth/request_code.py`, `backend/app/auth/verify_code.py`, `backend/app/auth/login_requests.py`, `backend/tests/auth/test_decoy_requests.py`
- Depends on: U-web-settings-17, U-web-settings-18, U-web-settings-24
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given an unknown and a known username, When a code is requested, Then both answers, cookies and cooldowns are the same and only the known one sends a mail (W-2) (type: security; level: api).
  2. Given a decoy request, When wrong codes are posted, Then `attemptsLeft` counts 4, 3, 2, 1 and the fifth kills the request and clears the cookie, as for a real one (type: security; level: api).
  3. Given a decoy request, When any code is posted, Then it is refused with the generic answer and no session is created (type: security; level: api).
  4. Given a wrong-format code on a decoy and on a real request, When posted, Then the two answers have the same shape and number (type: security; level: api).
  5. Given decoys, When requests are counted, Then they use the cooldown, the hourly cap and the in-process limits like real requests and expire with the existing retention (type: edge; level: db).
  6. Given the two paths, When timed over many runs, Then the medians differ by no more than the noise bound set in the test (type: security; level: api).

### U-web-settings-51: Limits before the session lookup, IPv6 per /64, bounded counters (R1; challenge fix; RT-03, RT-05, SEC-06)

- Layer: backend
- Contract: `limit("api")` runs before `session` on `GET /api/settings`, `PUT /api/settings`, `GET /api/places`, `GET /api/session` and `POST /auth/logout`; the route inventory requires a limit marker before the session marker on every non-probe route; `client_key` maps an IPv6 address to its /64 and an IPv4 address to itself; the limiter holds at most a configured number of counters per window and refuses new keys over it.
- Files: `backend/app/routers/{session,settings,places}.py`, `backend/app/core/security.py`, `backend/app/clientaddr.py`, `backend/app/limits.py`, `backend/app/limit_guard.py`, `backend/tests/test_route_inventory.py`, `backend/tests/test_limit_guard_api.py`, `backend/tests/test_limits.py`
- Depends on: U-web-settings-24
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pytest
- Criteria:
  1. Given 31 requests a minute without a session to each of the five routes, When sent, Then the 31st gets 429 and no session lookup runs for it (AC-16) (type: security; level: api).
  2. Given 31 requests from 31 addresses of one IPv6 /64, When sent to sign-in, Then the 31st gets 429; two different /64 networks have separate buckets (W-7, W-17) (type: security; level: unit).
  3. Given more distinct keys than the counter bound in one window, When another arrives, Then it is refused and memory stays bounded (type: edge; level: unit).
  4. Given the route inventory, When a route has the session marker without a limit marker before it, Then the test fails naming it (type: security; level: unit).

### U-web-settings-52: Chart sets the trusted proxies; production refuses an empty list (R1; challenge fix; RT-02, SEC-01)

- Layer: infra, backend
- Contract: the api Deployment renders `APP_TRUSTED_PROXY_CIDRS` and `APP_TRUSTED_PROXY_HOPS` from `api.config.trustedProxyCidrs` and `trustedProxyHops`; `values.schema.json` requires them when `ingress.enabled`; `validate_startup` refuses an empty CIDR list when the environment is production.
- Files: `deploy/charts/app/templates/workloads.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/envs/local/values.yaml`, `backend/app/startup.py`, `backend/tests/test_startup.py`, `backend/tests/test_chart_env.py`
- Depends on: U-web-settings-41
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-fastapi
- Criteria:
  1. Given the chart rendered with the local values, When the api env is read, Then both variables are present and the CIDR list is valid and non-empty (W-7, W-17) (type: security; level: chart).
  2. Given ingress enabled and no CIDR list, When the schema runs, Then it refuses (type: error; level: chart).
  3. Given environment production and an empty list, When the api starts, Then it exits non-zero naming the setting (type: security; level: unit).
  4. Given the chart env names, When compared with `Settings`, Then every name exists (existing test extended) (type: edge; level: unit).

### U-web-settings-53: The owner cannot be locked out by decoys, other clients or the cap (R1; challenge fix; ADR-0039; RT-01, RT-04, RT-06, SEC-02)

- Layer: backend, database (migration 0010)
- Contract: `web_auth.login_request` gains `client_hash` (keyed digest of the client key); decoys have their own open cap; a request for the configured username is never refused for decoy rows; open rows and codes per hour are also capped per `client_hash`; a new request replaces a live one only for the same login cookie or the same `client_hash`; every 429 carries the real remaining wait; the hourly cap counts from `created_at` for real and decoy rows alike.
- Files: `agents/mail-triage/migrations/versions/0010_login_request_client.py`, `backend/app/auth/login_requests.py`, `backend/app/auth/request_code.py`, `backend/app/auth/request_code_rules.py`, `backend/app/config.py`, `backend/tests/auth/test_decoy_requests.py`, `backend/tests/auth/test_request_code.py`, `backend/tests/auth/test_login_requests.py`
- Depends on: U-web-settings-50, U-web-settings-51
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 100 open decoy requests from one client, When the configured username asks for a code from another client, Then it gets 200 and a mail is sent (AC-16) (type: security; level: db).
  2. Given one client, When it opens more than the per-client number of requests or codes in an hour, Then it is refused while other clients are not (W-7) (type: security; level: db).
  3. Given Marco's live request in browser A, When another client asks for a code for his username, Then A's code still verifies; a request with A's cookie replaces it (type: security; level: db).
  4. Given a refused request, When the 429 is read, Then `Retry-After` equals the real time until the limit frees (type: edge; level: api).
  5. Given five requests then a sixth for a known and an unknown username at identical times, also when the mailer fails, When answered, Then status and `Retry-After` are identical (AC-30) (type: security; level: api).
  6. Given migration 0010, When run up, down and up, Then it is reversible and the web role gets only the grants it needs (type: edge; level: db).

### U-web-settings-54: Wrong codes are counted, the lock stops code mail, the mail text says what to do (R1; challenge fix; ADR-0039; RT-09, SEC-04, SEC-08, SEC-09)

- Layer: backend, database (migration 0011)
- Contract: `web_auth.security_event` gains `count`; a repeated `(kind, client_key, window)` increments it instead of being dropped; `client_key` is stored as a keyed digest; while the web lock is set, a code request answers as usual but creates no row and sends no mail; the code mail says that someone on the network knows the username if the code was not asked for and points to the Telegram Lock command.
- Files: `agents/mail-triage/migrations/versions/0011_security_event_count.py`, `backend/app/security_events.py`, `backend/app/auth/event_rules.py`, `backend/app/auth/request_code.py`, `backend/app/mail/message.py`, `backend/tests/db/test_security_events.py`, `backend/tests/auth/test_request_code.py`, `backend/tests/mail/test_message.py`
- Depends on: U-web-settings-53
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 5 wrong codes from one client in one minute, When recorded, Then one row with `count` 5 exists (W-13) (type: happy; level: db).
  2. Given a stored event, When read, Then `client_key` is a digest and no clear address is stored (type: security; level: db).
  3. Given the web lock is set, When a code is requested for the configured username, Then the answer is the same, no login request row is written and no mail is sent (AC-27) (type: security; level: api).
  4. Given the code mail, When rendered, Then it names the Lock command and contains no username or address of the sender (W-14, W-15) (type: security; level: unit).

### U-web-settings-55: Agent sets the web lock after repeated wrong codes (R1; challenge fix; ADR-0039; RT-07, SEC-03)

- Layer: agent
- Contract: when the summed `count` of `code_refused` events reaches 15 in 24 hours, the agent sets the web lock once and sends a Telegram notice (count, time; no code, username or address); Marco unlocks with `/web_unlock`; U-48 is the notice at 5 in 10 minutes.
- Files: `agents/mail-triage/app/usecases/code_alert.py`, `agents/mail-triage/app/db/pg_web_lock.py`, `agents/mail-triage/app/db/pg_security_events.py`, `agents/mail-triage/app/usecases/web_notice_actions.py`, `agents/mail-triage/app/usecases/dispatch.py`, `agents/mail-triage/app/core/settings_text.py`, `agents/mail-triage/app/wiring.py`, `agents/mail-triage/tests/usecases/test_code_lock.py`, `agents/mail-triage/tests/db/test_wrong_code_lock.py`
- Depends on: U-web-settings-48, U-web-settings-54
- Parallel: no
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given 15 wrong codes in 24 hours (`FakeClock`), When the agent runs, Then the lock is set and one notice is sent (W-13) (type: happy; level: agent).
  2. Given 14, or 15 over 24 hours 1 second, When it runs, Then nothing changes (type: edge; level: agent).
  3. Given a set lock, When the agent runs again, Then no second notice and no second write (type: edge; level: agent).
  4. Given `/web_unlock`, When Marco sends it, Then sign-in works again and the old events do not set the lock again (type: edge; level: agent).
  5. Given the sign-in mail names `/web_lock` (`LOCK_COMMAND`), When Marco sends `/web_lock` from the allowed chat, Then the lock is set and the agent confirms it and how to unlock; setting it again changes nothing and says it was already locked; from another chat nothing happens and nothing is answered (AC-27) (type: security; level: agent).
  6. Given events that were counted before a lock, or arrived while it was set, When `/web_unlock` lifts the lock, Then they never count again: the rule is that every event with an id at or below the newest id seen at the moment the lock is set, or seen while it is set, is spent; only newer events count (state of the rule: in memory, so a restart while unlocked forgets it and stale events inside 24 hours may set the lock once more, fail-closed) (type: edge; level: agent).
  7. Given the lock notice and the logs, When captured with canary values, Then no digest, username, address or code appears, and the notice names the count, the time and `/web_unlock` (W-13, W-15) (type: security; level: agent).
  8. Given the real agent role, When the lock is set and read, Then `web_lock` works and `security_event` stays read-only (type: security; level: db).

### U-web-settings-56: Undo burst is identified by an explicit id (R1; challenge fix; CR-07)

- Layer: agent, database (migration 0009)
- Contract: each Undo token record stores `burst_id` and `first_version`; the guard uses them instead of comparing `before` values; a partial send failure keeps the original burst.
- Files: `agents/mail-triage/migrations/versions/0009_notice_burst.py`, `agents/mail-triage/app/usecases/web_notice.py`, `agents/mail-triage/app/usecases/web_notice_actions.py`, `agents/mail-triage/tests/db/test_web_notice.py`
- Depends on: U-web-settings-27
- Parallel: yes
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given two bursts whose `before` values are equal inside 24 hours, When Undo is pressed on the older notice, Then only that burst is restored or refused as changed (AC-13) (type: edge; level: db).
  2. Given a send failure after the first notice of a burst, When retried and Undo is pressed on the first notice, Then the pre-burst values return (type: error; level: db).
  3. Given migration 0009, When run up, down and up, Then it is reversible (type: edge; level: db).

### U-web-settings-57: Ingress gates: HSTS, certificate alert, image digests (R1; challenge fix; RT-10, SEC-05, SEC-07)

- Layer: infra
- Contract: `values.schema.json` requires a non-empty HSTS mechanism when `hsts` is true; chart tests assert HSTS, the HTTP redirect and the TLS minimum for every environment values file that sets an ingress class; `certAlert.enabled` and an image `digest` are required when the environment is production; the base images of both Dockerfiles are pinned by `@sha256`. The ingress controller itself stays open (D-7, plan open points).
- Files: `deploy/charts/app/values.schema.json`, `deploy/charts/app/values.yaml`, `deploy/charts/app/templates/ingress.yaml`, `backend/Dockerfile`, `apps/web/Dockerfile`, `deploy/charts/app/tests/`
- Depends on: U-web-settings-41
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-docker, guardrail-tls-certificates
- Criteria:
  1. Given `hsts: true` and an empty annotation key, When the schema runs, Then it refuses (AC-18) (type: error; level: chart).
  2. Given each environment values file, When rendered, Then an HSTS directive, an HTTP redirect and the minimum TLS version are present or the test names what is missing (AC-18) (type: security; level: chart).
  3. Given production values without `certAlert.enabled` or a digest, When the schema runs, Then it refuses (W-9) (type: security; level: chart).
  4. Given both Dockerfiles, When linted, Then every `FROM` has a digest (type: security; level: unit).

### U-web-settings-58: TLS with verify-full for the agent and the migrate job (R1; challenge fix; SEC-10)

- Layer: infra, agent
- Contract: the agent runtime and the migrate job connect with `sslmode=verify-full` and the CA; `pg_hba.conf` uses `hostssl` for every role in the prod-like stack; the worker chart carries the CA and the setting.
- Files: `agents/mail-triage/app/settings.py`, `agents/mail-triage/app/db/engine.py`, `deploy/charts/worker/`, `deploy/prod-like/pg_hba.conf`, `compose.yaml`, `agents/mail-triage/tests/infra/`
- Depends on: U-web-settings-39
- Parallel: yes
- Guardrails: guardrail-tls-certificates, guardrail-helm, guardrail-compose, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the agent role connecting without TLS in the prod-like stack, When it tries, Then the server refuses (W-8, W-9) (type: security; level: prod-like).
  2. Given the worker chart, When rendered, Then the CA and `verify-full` are set for the runtime and the migrate job (type: security; level: chart).
  3. Given the agent settings in production, When `sslmode` is weaker than `verify-full`, Then start-up refuses (type: error; level: unit).

### U-web-settings-59: Safe defaults and response headers (R1; challenge fix; SEC-11, SEC-12, CR-09, CR-11)

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

### U-web-settings-60: One cookie builder, current attemptsLeft docs, one retention constant (R1; challenge fix; CR-03, CR-04, CR-10)

- Layer: backend
- Contract: `app/auth/cookies.py` builds and clears every `__Host-` cookie; `client_key` lives next to `clientaddr`; the verify-code description says `attemptsLeft` is present for a real or decoy login request and the generated files are rebuilt; one `LOGIN_REQUEST_RETENTION` constant; expired sessions and login requests are purged on the first request of each hour as well as at start-up.
- Files: `backend/app/auth/cookies.py`, `backend/app/auth/session.py`, `backend/app/auth/request_code.py`, `backend/app/auth/verify_code.py`, `backend/app/routers/auth.py`, `backend/app/startup.py`, `docs/api/openapi.json`, `docs/api/reference.md`, `apps/web/src/api/schema.d.ts`, `backend/tests/auth/test_cookies.py`
- Depends on: U-web-settings-53, U-web-settings-54
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-python, guardrail-pytest
- Criteria:
  1. Given each cookie, When set or cleared, Then it is `__Host-`, Secure, HttpOnly, SameSite=Lax, Path=/ and has no Domain (AC-7) (type: security; level: unit).
  2. Given the generated API files, When regenerated, Then the check passes and the `attemptsLeft` text matches AC-3 (type: edge; level: unit).
  3. Given expired rows and one hour passing (`FakeClock`), When the next request arrives, Then they are purged once (type: edge; level: db).

### U-web-settings-61: Conflict marks name where the other change came from (R1; challenge fix; RT-08)

- Layer: web
- Contract: the conflict marks and buttons derive their wording from `updatedVia` (web or Telegram).
- Files: `apps/web/src/features/settings/ConflictLayer.tsx`, `apps/web/src/features/settings/useConflict.ts`, `apps/web/src/features/settings/ConflictLayer.test.tsx`
- Depends on: U-web-settings-35
- Parallel: yes
- Guardrails: guardrail-react, guardrail-vitest-rtl, guardrail-a11y
- Criteria:
  1. Given a 409 whose row has `updatedVia` web, When the marks render, Then they say the web now has the value and the button says to keep the stored value (W-11, W-12) (type: security; level: component).
  2. Given `updatedVia` Telegram, When rendered, Then the wording names Telegram (type: happy; level: component).
  3. Given both, When axe runs, Then no violation (type: a11y; level: component).

### U-web-settings-62: Test hygiene: no silent skips, structural decoy check (R1; challenge fix; CR-02, CR-05, CR-12)

- Layer: backend, web tests
- Contract: database fixtures fail instead of skip when `CI` is set and skip only for Docker-unavailable errors; a CI step asserts a minimum number of database tests ran; the decoy equality test compares the recorded database and mail-queue steps of both paths and the wall-clock comparison runs only in the mutation workflow behind a marker; the contract fixture filters its cases before generating; the journey uses web-first assertions instead of `setTimeout`.
- Files: `backend/tests/db/conftest.py`, `backend/tests/db/test_database_tls.py`, `backend/tests/db/test_contract_fixture.py`, `backend/tests/auth/test_decoy_requests.py`, `.github/workflows/ci.yml`, `apps/web/e2e/journey.spec.ts`
- Depends on: U-web-settings-53
- Parallel: no
- Guardrails: guardrail-pytest, guardrail-playwright
- Criteria:
  1. Given `CI` is set and the container cannot start, When the database tests run, Then the run fails (type: security; level: unit).
  2. Given the backend job, When it ends, Then it fails if fewer than the stated number of database tests ran (type: security; level: ci).
  3. Given a known and an unknown username, When requested, Then the recorded steps are equal (AC-30) (type: security; level: api).

### U-web-settings-63: The lock counts only wrong codes against a live request (R1; challenge round 2; ADR-0039 amendment; SEC2-01, RT2-01)

- Layer: backend (agent unchanged)
- Contract: `verify-code` records `code_refused` only for a well-formed wrong, expired or exhausting code against a login request that exists (real or decoy); a request without a login cookie, with a malformed body, or for a dead, unknown or replaced request records `code_invalid` instead, a kind that never counts towards the alert or the lock and is deduplicated like the other uncounted kinds. The answers to the visitor do not change (AC-30).
- Files: `backend/app/auth/verify_code.py`, `backend/app/auth/event_rules.py`, `backend/tests/auth/test_verify_code.py`, `backend/tests/auth/test_event_rules.py`, `backend/tests/db/test_security_events.py`
- Depends on: U-web-settings-54
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pytest
- Criteria:
  1. Given no login request, When 20 posts arrive from one client without cookie, with body `{}` and with a well-formed code and an unknown cookie, Then the sum of `count` of `code_refused` is 0 and `code_invalid` holds them (W-13) (type: security; level: db).
  2. Given a live login request, When 5 wrong well-formed codes are posted with its cookie, Then the sum of `count` of `code_refused` is 5 (type: happy; level: db).
  3. Given a decoy login request, When wrong codes are posted, Then they count as `code_refused` like for a real one (AC-30) (type: security; level: db).
  4. Given the agent suite, When 50 `code_invalid` events exist, Then no alert and no lock (type: security; level: agent).

### U-web-settings-64: A full decoy class is invisible, replace by cookie only, limiter keeps room for the owner (R1; challenge round 2; RT2-03, RT2-04, RT2-05)

- Layer: backend
- Contract: when the decoy class is full, a request for an unknown username is answered like any other (200, cookie, no code sent) but no row is stored, so it never refuses where the owner would not (AC-30); a new request replaces a live one only when it carries the same login cookie, never by `client_hash` alone; the limiter, when the counter bound is reached, evicts the oldest keys (or refuses only keys that are new and carry no valid session or login cookie) so many keys cannot refuse the owner; the limiter keys IPv6 per /64 with a second bound per /48.
- Files: `backend/app/auth/login_requests.py`, `backend/app/auth/request_code.py`, `backend/app/limits.py`, `backend/app/clientaddr.py`, `backend/tests/auth/test_decoy_requests.py`, `backend/tests/test_limits.py`
- Depends on: U-web-settings-53, U-web-settings-51
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 100 live decoy rows, When a code is requested for an unknown name and for the configured name from a fresh client, Then status, headers apart from the cookie value and body shape are identical (AC-30) (type: security; level: api).
  2. Given the owner's live request in browser A and another device in the same /64, When that device asks for the configured username without A's cookie, Then A's request is still live; a request with A's cookie replaces it (type: security; level: db).
  3. Given the limiter at its counter bound, When a new key carries a valid session cookie, or a key seen in the previous window arrives, Then it is allowed; 10000 keys from one /48 cannot refuse the owner (type: security; level: unit).
  4. Given the mutation gate, When `limits.py` and `clientaddr.py` are mutated, Then survivors stay at 0 (type: edge; level: unit).

### U-web-settings-65: Contract version, count integrity, column grants, event index (R1; challenge round 2; SEC2-02, SEC2-03, RT2-06, RT2-09)

- Layer: database (migration 0012), backend, agent
- Contract: migration 0012 raises `settings.contract_version()` and the backend `EXPECTED_CONTRACT_VERSION` (down lowers it), so `/readyz` is 503 on a database older or newer than the api; a `BEFORE UPDATE` trigger on `web_auth.security_event` allows only `NEW.count = OLD.count + 1` with every other column unchanged, plus `CHECK (count >= 1)`; the agent role gets `SELECT (id, kind, at, count)` only; an index on `(kind, at)`.
- Files: `agents/mail-triage/migrations/versions/0012_event_integrity.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/db/models.py`, `backend/app/db.py`, `agents/mail-triage/tests/db/test_event_integrity_migration.py`, `backend/tests/db/test_readiness_contract.py`
- Depends on: U-web-settings-54, U-web-settings-48
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-fastapi, guardrail-pytest
- Criteria:
  1. Given the chain at 0009, 0010 or 0011, When `/readyz` runs, Then 503; at 0012, Then 200 (type: security; level: db).
  2. Given the web role, When it sets `count` to 0, to old+2 or changes any other column, Then it is refused; `count + 1` works (W-8, W-13) (type: security; level: db).
  3. Given the agent role, When it selects `username_hash`, `client_key` or `request_id` from `security_event`, Then 42501; `id`, `kind`, `at` and `count` work (type: security; level: db).
  4. Given the alert query on a large table, When explained, Then it uses the `(kind, at)` index (type: edge; level: db).
  5. Given migration 0012, When run up, down and up, Then it is reversible (type: edge; level: db).

### U-web-settings-66: Chart: environment cannot be overridden, digests everywhere (R1; challenge round 2; RT2-08, SEC2-05)

- Layer: infra
- Contract: the app chart renders `APP_ENVIRONMENT` from `.Values.environment` and fails when `api.env` or `web.env` sets `APP_ENVIRONMENT`, `APP_DATABASE_*`, `APP_TRUSTED_PROXY_*` or any limit key (`APP_*_PER_*`, `APP_CODES_PER_HOUR`, `APP_MAX_ATTEMPTS`); the agent Dockerfile and the Caddy image are pinned by `@sha256`; the worker chart gets a values schema that requires a digest when `environment` is production; the digest lint covers every Dockerfile and compose image in the repo.
- Files: `deploy/charts/app/templates/workloads.yaml`, `deploy/charts/app/values.schema.json`, `deploy/charts/worker/values.schema.json`, `deploy/charts/worker/values.yaml`, `agents/mail-triage/Dockerfile`, `compose.yaml`, `agents/mail-triage/tests/infra/test_ingress_gates.py`
- Depends on: U-web-settings-57, U-web-settings-58
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-docker, guardrail-kubernetes, guardrail-compose
- Criteria:
  1. Given environment production and `api.env.APP_ENVIRONMENT=development` or `APP_CODES_PER_HOUR=1000`, When `helm template` runs, Then it fails naming the key (type: security; level: chart).
  2. Given worker values with environment production and no digest, When the schema runs, Then it refuses (type: security; level: chart).
  3. Given every Dockerfile and compose image in the repo, When linted, Then each has `@sha256` or an explicit documented exception (type: security; level: unit).

### U-web-settings-67: Digest domain separation, IPv6 event class (R1; challenge round 2; SEC2-07, SEC2-08)

- Layer: backend
- Contract: the client digest uses its own derived subkey (`HMAC(key, b"client-key")`) so no username can collide with a client digest; `client_class` classifies a `/64` key as `ipv6`.
- Files: `backend/app/auth/request_code_rules.py`, `backend/app/auth/event_rules.py`, `backend/tests/auth/test_request_code_rules.py`, `backend/tests/auth/test_event_rules.py`
- Depends on: U-web-settings-64, U-web-settings-63
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given the username `client:10.0.0.5`, When hashed, Then `username_key` differs from `client_hash` of `10.0.0.5` (type: security; level: unit).
  2. Given an IPv6 `/64` key, When classified, Then the class is `ipv6` (type: edge; level: unit).
  3. Given the mutation gate, When both modules are mutated, Then survivors stay at 0 (type: edge; level: unit).

### U-web-settings-68: The lock counts only wrong codes against the owner's real requests; an expired request dies on its first post (R1; challenge round 3; ADR-0039 amendment 2; RT3-01, RT3-04, SEC3-01)

- Layer: backend
- Contract: `check()` in `login_requests.py` knows the owner key (`username_key` of the configured username); a well-formed wrong, expired or exhausting code counts as `code_refused` only against a row whose `username_key` equals the owner key; a guess against a decoy row is recorded as `code_invalid`; when `check()` meets an expired row it sets `dead_at` in the same locked transaction and returns `Dead(existing=True)` only that first time, later posts get `Dead()`. The answers to the visitor stay identical for real and decoy rows (AC-30).
- Files: `backend/app/auth/login_requests.py`, `backend/app/auth/verify_code.py`, `backend/app/auth/event_rules.py`, `backend/tests/auth/test_verify_code.py`, `backend/tests/auth/test_login_requests.py`, `backend/tests/db/test_security_events.py`, `agents/mail-triage/tests/db/test_wrong_code_lock.py`
- Depends on: U-web-settings-63, U-web-settings-67
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given no request for the configured username, When one client asks codes for three unknown names and posts 5 well-formed wrong codes with each cookie, Then the sum of `code_refused` is 0, `code_invalid` holds them and the agent does not set the lock (W-13, R-3) (type: security; level: db).
  2. Given the owner's live request, When 5 wrong codes are posted, Then the sum of `code_refused` is 5 (type: happy; level: db).
  3. Given a request 11 minutes old, When 10 well-formed codes are posted with its cookie, Then `code_refused` is 1 and the other nine are `code_invalid` (type: security; level: db).
  4. Given a decoy and an owner request, When wrong codes are posted, Then status, body and `attemptsLeft` are the same shape (AC-30) (type: security; level: api).

### U-web-settings-69: No swallowed decoys, and the lock leaves no trace (R1; challenge round 3; ADR-0039 amendment 2; RT3-02, RT3-03)

- Layer: backend
- Contract: the global decoy cap (`open_login_request_cap`, the swallow branch of U-64) is removed; decoy storage stays bounded by the per-client caps (10 open, 20 per hour), the limiter and the one-hour purge, and a decoy is always stored with its own cooldown, hourly count and attempt counter; while the web lock is set a request is still stored (the owner's row with an unmatchable hash like a decoy, so no code can match) and only the mail is skipped, so cooldown, caps and `attemptsLeft` behave the same locked and unlocked (AC-27, AC-30). Rebuild, no flag.
- Files: `backend/app/auth/login_requests.py`, `backend/app/auth/request_code.py`, `backend/app/config.py`, `backend/tests/auth/test_decoy_requests.py`, `backend/tests/auth/test_request_code.py`, `backend/tests/auth/test_login_requests.py`, `backend/tests/test_login_request_limits_config.py`
- Depends on: U-web-settings-68
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 100 live decoy rows from 10 clients, When a fresh client asks twice within 60 s for an unknown name and twice for the configured name and posts one wrong code with each cookie, Then the second answers have the same status and `Retry-After` and the verify answers have the same `attemptsLeft` presence (AC-30) (type: security; level: api).
  2. Given the web lock is set and then lifted, When a random name is requested twice within 60 s in each state and a wrong code is posted with that cookie, Then the answers are the same in both states and no mail is sent while locked (AC-27) (type: security; level: api).
  3. Given many clients, When each stays within its per-client caps, Then no request is swallowed and the table size is bounded by clients times the per-client cap (type: edge; level: db).
  4. Given the settings, When loaded, Then `open_login_request_cap` no longer exists and the chart's forbidden-key list stays consistent with `Settings` (type: edge; level: unit).

### U-web-settings-70: Chart: case-insensitive env guards, pinned test image, a disruption budget that allows one eviction (R1; challenge round 3; RT3-06, RT3-08, SEC3-08)

- Layer: infra
- Contract: both charts compare env keys case-insensitively against every key the chart sets itself (plain and secret) and against the forbidden lists (worker: `ENVIRONMENT`, `DATABASE_*`; app: the U-66 list); the Helm test pod image is pinned by `@sha256` and the digest lint covers `deploy/charts/**/templates`; the api PodDisruptionBudget allows one disruption (`maxUnavailable: 1`), and the schema refuses `minAvailable >= api.replicas`.
- Files: `deploy/charts/app/templates/_helpers.tpl`, `deploy/charts/worker/templates/_helpers.tpl`, `deploy/charts/app/templates/tests/test-health.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `agents/mail-triage/tests/infra/`
- Depends on: U-web-settings-66
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-docker
- Criteria:
  1. Given `env.database_ssl: disable` on the worker or `api.env.app_public_origin` on the app, When `helm template` runs, Then it fails naming the key (type: security; level: chart).
  2. Given every image in `deploy/charts/**/templates`, When linted, Then each has `@sha256` (type: security; level: unit).
  3. Given production values, When rendered, Then the api PodDisruptionBudget allows one disruption; `minAvailable: 1` with one replica is refused by the schema (type: edge; level: chart).

### U-web-settings-71: The web role cannot forge security events; expired notice tokens are purged (R1; challenge round 3; RT3-05, SEC3-04)

- Layer: database (migration 0013), agent
- Contract: migration 0013 grants the web role `INSERT` on `web_auth.security_event` only for `(kind, result, username_hash, request_id, client_key, "window")`, makes `id` `GENERATED ALWAYS`, and adds a `BEFORE INSERT` trigger that sets `at = now()`, `count = 1` and `window = floor(extract(epoch from now()) / 60)`; the retention purge also deletes `web_notice_token` rows whose `expires_at` has passed.
- Files: `agents/mail-triage/migrations/versions/0013_event_insert_guard.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/app/db/purge.py`, `agents/mail-triage/tests/db/test_event_insert_guard.py`, `agents/mail-triage/tests/db/test_purge.py`
- Depends on: U-web-settings-65, U-web-settings-49
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the web role, When it inserts a `security_event` with an explicit `id`, `at` or `count`, Then it is refused (42501); a normal insert works and gets the server's `at`, `count` 1 and window (W-8, W-13) (type: security; level: db).
  2. Given an expired and a live notice token, When the purge runs, Then only the expired one is gone (W-11) (type: happy; level: db).
  3. Given migration 0013, When run up, down and up, Then it is reversible (type: edge; level: db).

## Coverage of the acceptance criteria

| AC | Units |
| --- | --- |
| AC-1 | 20, 25, 32, 34, 42, 43 |
| AC-2 | 15, 20, 22, 23, 28, 43 |
| AC-3 | 10, 11, 16, 18, 25, 30, 31, 42, 43, 50, 60 |
| AC-4 | 04, 38 |
| AC-5 | 11, 16, 17, 18, 31 |
| AC-6 | 10, 18, 30 |
| AC-7 | 11, 15, 18, 19, 25, 28, 42, 60 |
| AC-8 | 17, 18, 19, 22, 28, 45, 47 |
| AC-9 | 06, 21, 22, 25, 32, 42 |
| AC-10 | 20, 21, 22, 32 |
| AC-11 | 21, 22, 35, 43, 45, 46, 47, 61 |
| AC-12 (first half, R1) | 28, 30, 43 |
| AC-12 (second half, R2) | 47 |
| AC-13 | 26, 27, 34, 45, 56 |
| AC-14 | 01, 05, 22, 28, 30, 32, 33, 43 |
| AC-15 | 05, 14, 17, 18, 19, 20, 22, 23, 28, 45 |
| AC-16 | 16, 17, 20, 22, 24, 38, 40, 51, 52, 53 |
| AC-17 | 06, 07, 21, 22, 39, 42, 49, 65, 71 |
| AC-18 | 04, 37, 40, 43, 57, 66, 70 |
| AC-19 | 05, 37, 40, 43, 59 |
| AC-20 (first half) | 13, 14, 15, 17, 18, 19, 24, 37, 42 |
| AC-20 (second half, R1 since ADR-0039) | 48, 54, 55, 63, 65, 68, 71 |
| AC-21 (R1 since D-19) | 49, 65, 71 |
| AC-22 | 01, 29, 31, 32, 33, 36, 43, 46 |
| AC-23 | 01, 29, 30, 31, 32, 33, 34, 35, 36, 46, 47 |
| AC-24 | 30 |
| AC-25 (R2) | 45, 46 |
| AC-26 | 20, 21, 25 |
| AC-27 | 15, 18, 20, 22, 27, 31, 43, 54, 55, 69 |
| AC-28 | 33, 34, 35, 43, 47, 61 |
| AC-29 | 12, 13, 16, 17, 38, 54 |
| AC-30 | 17, 30, 50, 53, 62, 63, 64, 68, 69 |
| AC-31 | 11, 16, 17, 31, 53, 54, 64 |
| AC-32 (added in the build) | 48, 55, 63, 68, 69 |
| AC-33 (added in the build) | 63, 68 |

Check (run mechanically from the criteria tags): AC-1 to AC-33 all appear; only the second half of AC-12 and AC-25 are in R2 units (U-45 to U-47), which are not built. U-52, U-58, U-66, U-67 and U-70 have no acceptance criterion of their own; they are listed under the threats below.

## Coverage of the threats

| Threat | Units |
| --- | --- |
| W-1 | 04, 10, 16, 18, 31 |
| W-2 | 10, 17, 18, 50 |
| W-3 | 15 |
| W-4 | 17, 19, 28, 47 |
| W-5 | 05, 32, 43, 59 |
| W-6 | 05, 37, 40 |
| W-7 | 09, 16, 17, 24, 31, 41, 51, 52, 53, 64, 66, 67, 70 |
| W-8 | 06, 07, 09, 39, 41, 42, 58, 65, 71 |
| W-9 | 09, 37, 39, 40, 41, 57, 58, 66 |
| W-10 | 06, 10, 21, 45 |
| W-11 | 26, 27, 56, 61, 71 |
| W-12 | 21, 29, 32, 36, 61 |
| W-13 | 05, 06, 13, 14, 24, 37, 48, 49, 54, 55, 63, 65, 68, 71 |
| W-14 | 04, 12, 38, 54 |
| W-15 | 04, 06, 10, 12, 13, 14, 16, 17, 18, 19, 23, 25, 30, 33, 42, 48, 54, 55 |
| W-16 | 04, 12, 13, 41 |
| W-17 | 24, 40, 41, 51, 52 |

Check (run mechanically from the criteria tags): W-1 to W-17 all appear; U-51 to U-71 are each listed in at least one row of the two tables above (U-60 under AC-3 and AC-7, U-62 under AC-30, U-67 under W-7).

## Units that touch the same files or tests

These units must be merged one at a time, each with `main` merged in first and the full suite green before the merge (lesson of `adjustable-quiet-hours`: parallel branches that edit the same file or fixture break each other silently). Units that are parallel in the diagram are parallel for the build, not for the merge.

| Shared file or test | Units, in merge order |
| --- | --- |
| `backend/pyproject.toml`, `backend/uv.lock` | 02, 09, 12, 44 |
| `backend/Dockerfile` | 02, 14 |
| `backend/app/main.py` | 04, 05, 14 |
| `backend/app/config.py`, `backend/app/startup.py` | 04, 09 |
| `backend/app/middleware.py`, `backend/app/limit_guard.py` | 05, 24 |
| `backend/app/core/security.py` | 05, 15, 19 |
| `backend/app/routers/auth.py` | 17, 18, 19 |
| `backend/app/routers/settings.py` | 20, 22, 45 |
| `backend/app/settings_repo.py` | 20, 21 |
| `backend/tests/test_route_inventory.py` | 05, 23, 45 |
| `docs/api/openapi.json` (generated; regenerate after each merge) | 05, 17, 18, 19, 20, 22, 23, 45 |
| `backend/tests/conftest.py` | 03 only |
| `backend/tests/db/conftest.py` | 09 only |
| `backend/tests/fakes.py` | 03 only; later units add fakes in their own modules |
| `agents/mail-triage/migrations/versions/0008_web_auth.py`, `app/db/models.py` | 06 only; no later unit may edit 0008 |
| `agents/mail-triage/app/db/grants.sql` | 07, 48 |
| `agents/mail-triage/tests/db/test_settings_grants.py`, `test_settings_migration.py` | 06, 07 |
| `agents/mail-triage/app/db/migrate.py`, `app/settings.py`, `tests/db/test_migrate_job.py` | 08, 49 |
| `agents/mail-triage/compose.yaml` | 08 only |
| `agents/mail-triage/app/runner.py`, `app/core/settings_text.py` | 26, 27, 48 |
| `agents/mail-triage/app/usecases/dispatch.py` | 27 only |
| `packages/schedule-policy/schedule_policy/policy.py`, `__init__.py`, `contract/settings_cases.json` | 20 only |
| `apps/web/package.json`, `pnpm-lock.yaml`, `apps/web/vite.config.ts` | 28, then any unit that adds a dependency (30, 33) |
| `apps/web/src/main.tsx`, `src/App.tsx` | 28 only (routes are fixed there) |
| `apps/web/src/api/schema.d.ts` (generated) | 28, then regenerate in 30, 32, 45 |
| `apps/web/src/pages/LoginPage.tsx`, `CodeStep.tsx` | 30, 31, 47 |
| `apps/web/src/features/settings/SettingsForm.tsx` | 32 only (slot files carry the later work) |
| `apps/web/src/features/settings/ZoneField.tsx` | 32, 33 |
| `apps/web/src/features/settings/SaveFeedback.tsx` | 32, 34 |
| `apps/web/src/features/settings/ConflictLayer.tsx` | 32, 35 |
| `apps/web/src/features/settings/ResetSlot.tsx` | 32, 46 |
| `apps/web/e2e/ui-states.spec.ts`, `apps/web/playwright.config.ts` | 36, 37, 43, 46 |
| `apps/web/Dockerfile`, `apps/web/nginx.conf` | 37 only |
| `compose.yaml` | 02, 37, 38, 39 |
| `.github/workflows/ci.yml` | 02, 08, 37, 42 |
| `.github/workflows/mutation.yml` | 44 only |
| `deploy/charts/app/values.yaml`, `values.schema.json` | 40, 41 |
| `deploy/charts/worker/templates/migration.yaml`, `README.md` | 08 only |

Rule: if two units of one row are built in parallel, the second to finish rebases on `main` after the first merges and re-runs its full suite, then regenerates the generated files (`openapi.json`, `schema.d.ts`, lockfiles) instead of merging them by hand.

## Decisions needed

Needed before staging; none of them blocks the build, the tests or the prod-like stack.

| # | Question | Why it matters | Units |
| --- | --- | --- | --- |
| D-7 | Where the certificate expiry alert (at least 14 days ahead, W-9) is delivered. U-41 ships an optional `PrometheusRule`, off by default; whether the cluster has a Prometheus (ADR-0013 does not decide) and who is notified is open. | Expiry is a W-9 control and a gate for production, not for the build. | 41 |
| D-9 | The private certificate authority for production: a CA Marco runs by hand, or a cert-manager CA issuer in the cluster; how Marco's devices trust it. | The chart takes the issuer from values; the choice sets the rotation and the expiry alert. | 40, 41 |
| D-10 | The send-only SMTP account and relay for production (provider, port, whether the relay supports STARTTLS with a public certificate or needs a private CA). | The start-up check and the NetworkPolicy need the real host and port; a relay with a private CA would need a CA setting in the api that the design excludes. | 04, 12, 41 |

## Decided

Approved by Marco on 2026-11-10 (phase 4 gate):

- D-1 `noticeIntervalMinutes` in `GET /api/session` (U-19, U-34).
- D-2 fonts are self-hosted, because the CSP blocks Google Fonts (U-01, note in ADR-0035).
- D-3 the unlock command is `/web_unlock` (U-27).
- D-4 and D-5 are gone with the identity provider; failures are inline on the login page.
- D-6 the R2 draft lives in `sessionStorage` (U-47).
- D-8 `updatedAt` and `updatedVia` are null at version 0 (U-20).
- D-11 (replaced by D-16 on 2026-11-13) a failed send starts the 60 second cooldown but did not count towards the 5-codes-per-hour cap, so a mail outage cannot lock Marco out (ADR-0036, spec AC-29 and AC-31; U-06, U-11, U-16, U-17).
- D-12 a locked web gives the same generic refusal as any other refused request, with no explanation of the lock; the screens document has no locked state (U-18, U-31, U-43).
- D-16 every code request counts towards the 5 an hour, also one whose send failed, for known and unknown usernames alike; AC-30 wins over D-11 (Marco, 2026-11-13; U-53). With the mailer down Marco waits at most an hour; each failure stays a `mail_failed` event.
- D-14 the owner cannot be locked out by decoys or other clients; limits per client, IPv6 per /64 (Marco, 2026-11-13; ADR-0039; U-51, U-52, U-53, U-54).
- D-15 the wrong-code alert moves into R1 and 15 wrong codes in 24 hours set the web lock (Marco, 2026-11-13; ADR-0039; U-48, U-55).
- D-17 the alert and the lock count only wrong codes against an existing login request (real or decoy); no-cookie, malformed and dead-request refusals are `code_invalid` and never count (challenge round 2, SEC2-01; ADR-0039 amendment; U-63).
- D-18 a person who knows the username can use up the 5 codes an hour from one device; accepted as R-4 until the review of 2027-05-10 (Marco, 2026-11-13; RT2-02).
- D-19 U-49 (retention purge, 90 days for security events, one year for audit) and an index on `(kind, at)` move into R1 and are a gate before production (Marco, 2026-11-13; U-49, U-65).
- D-20 the lock counts only wrong codes against the owner's real requests, there are no swallowed decoys and the lock leaves no trace (challenge round 3, moderator decision; ADR-0039 amendment 2; U-68, U-69, U-71).
- D-21 the ingress controller is its own decision, still open; HSTS, redirect and TLS minimum are a gate before production (round 3, SEC3-02, formerly mixed up with D-7 which is the certificate expiry alert).
- D-13 unknown usernames get a decoy login request and `attemptsLeft` is shown every time (Marco, 2026-11-12; ADR-0038; U-50). This replaces the earlier rule "`attemptsLeft` only for a live login request".
- Fixed inside the units: cookie lifetimes (`__Host-login` Max-Age 600, `__Host-session` Max-Age 43200), HSTS without `includeSubDomains`, the SMTP library (`aiosmtplib`), and `attemptsLeft` in the generic verify failure body for any login request cookie, real or decoy (D-13).

## Open points

- Hosting (ADR-0012, ADR-0037): the local host name, the cluster and the ingress controller are decided before staging. The build and all tests run against the prod-like stack and do not wait. The controller-specific ingress settings (8 KB body cap, TLS minimum, log format without the query string) are per-environment values (U-40); the pinned log format is settled with the controller.
- The agent run interval for the page text: `noticeIntervalMinutes` is set from one chart value that the worker chart also uses (`POLL_INTERVAL_SECONDS` is 60 in compose); the production value is set when the cluster values exist.
- Two-step verification on Marco's mailbox is a condition for production (R-1); R-1 is reviewed on 2027-05-10. R-2 (anything on the local network can reach the login page) is bounded by U-24 and U-16.
- The agent is not in the prod-like stack, so web notices, Undo and the lock are tested at agent level with a real database (U-26, U-27), and the api side of the lock in U-15, U-18 and U-43. A full chain test across both belongs to staging.
- Documentation (phase 8) is not a unit here: the user-guide page for the settings page with screenshots, the API guide and the generated reference are written from what is built.
- Total: 72 units (69 in R1, 3 in R2; U-68 to U-72 come from challenge round 3; U-49 moved into R1 as well and U-63 to U-67 come from challenge round 2; U-48 moved into R1 and U-51 to U-62 are challenge fixes), above the target of about 35 and the later ceiling of about 40. The excess comes from the QA splits (clock and code source, security events and logging hygiene, the TLS edge, the TLS database and the mail catcher, CI sequence and journey) and the sign-in units the e-mailed code adds (code rules, mail sender, login request store, two endpoints, two login-page units). Merge candidates if fewer are wanted: U-10 with U-11, U-30 with U-31, U-40 with U-41, U-13 with U-14, U-25 with U-22; each merge costs single responsibility.

## Changes made during the build

Filled in while building, in the manner of `adjustable-quiet-hours`. Carried over as rules:

- Anything found by the challenge round (phase 6) gets its own fix unit `U-web-settings-<nn>` with the source of the finding named, and runs in parallel only when it shares no file with another.
- First mutation run of U-44 (2026-11-12), all 12 marked pure modules, cosmic-ray 8.7.0, annotation mutants skipped (equivalent on CPython 3.14), gate 15 % survivors, target 10 %:
  - Linux, workflow `mutation` run 43319415821 (manual start, one job per module on CPython 3.14): 0.00 % survived for every module. Skipped annotation mutants: csrf 33, clientaddr 55, verify_code_rules 22, request_code_rules 22, code_rules 11, return_to 11, the others 0. The slowest job (`limits.py`) took 59 minutes of the 120 minute limit.
  - Windows, local foreground runs of `uv run python mutation/run.py <module>` (CPython 3.13.14): 0.00 % survived for every module (`code_hash`, `code_rules`, `csrf`, `digest`, `event_rules`, `expiry`, `mask`, `request_code_rules`, `return_to`, `verify_code_rules`, `clientaddr`, `limits`). No survivor, so the exclusion list `backend/mutation/code_rules.exclusions` stays empty.
  - The first attempt (run 43297283455, all modules serial in one job) hit the 120 minute job timeout and was cancelled; the workflow now has a `backend-matrix` job that reads the module list from `backend/cosmic-ray.toml` and a `backend` job per module.
- Migration numbers are checked against `main` before each merge.
- Phase 6 challenge (2026-11-13), reports by red-team, security-architect and code-reviewer on `main` 67b137e: no Critical, two High (decoy lock-out, chart without trusted proxies); Medium and Low are fixed by U-51 to U-62, decisions in ADR-0039. Not fixed here: CR-01 (`scripts/architecture.mjs` arrives with the kit upgrade PR; run the architecture check after it merges), CR-06 (user guide, phase 8), CR-08 (hand-written boundary validation in `apps/web`, a Low follow-up), the ingress controller choice (D-7).

Follow-ups found while building (2026-11-12), each to be handled by the named unit or a fix unit:

- U-38 must remove the temporary legacy `create_app()`, add `smtp_from` (the chart already passes `APP_SMTP_FROM`), verify the chart env names against `backend/app/config.py`, and call `attach_database`, `attach_sessions`, `attach_request_code` and `attach_verify_code` in the production factory; until then readiness is fail-open and `app.state.verify_code` does not exist in the running app.
- U-38 (done): the legacy `create_app()` is gone; `app.production:create_production_app` is the one factory (image and `api-dev`), `smtp_from` is a setting and the From address, readiness without a database is 503, and a test compares the chart and compose env names with `Settings`. The `mail` service now belongs to the `prod-like` profile only (it needs the certificate of the internal CA and nothing else used it); `api-dev` gets the same settings by reference and runs without a TLS database or catcher. The CI jobs `runtime-role` and `gxp` carry the new `.env` references.
- U-18 returns 204 for a successful verify-code and the validated path in an `X-Return-To` header, because 204 has no body; the login page always goes to `/settings` (U-31).
- `security_events.username_hash` is `CHAR(64)` and holds a 32-character digest, so it is space padded on read; compare with the padding stripped, or change the column in a later migration.
- `login_request.id` is `VARCHAR(32)`; U-16 uses `ids.token(24)`; later units use the id returned in `LoginRequest`.
- U-26 selects only `db_role='web_settings_runtime'` notices; the cursor is null at migration, which avoids a first-run flood.
- `UNBUILT_PATHS` in the route inventory test was removed in U-18; the inventory is exact again.
- U-10 and U-11 mutation approaches differ; U-44 (done) unifies them: `backend/cosmic-ray.toml` is the single list (12 modules, also read by `tests/test_pure_modules.py`), `mutation/run.py` runs one module or `--all`, and `tests/test_mutation_config.py` fails when a marked module is not listed.
- Duplicate `RETENTION` constants (`login_requests.py` and `startup.py`); the 503 body in readiness differs from the U-05 error model; the CSP also applies to dev-only `/docs`.
- Open before staging: ingress-controller vocabulary is ingress-nginx while kind uses Traefik; the api PodDisruptionBudget default `minAvailable: 1` with one replica.
- Tooling: the worktree isolation of the Agent tool refuses a primary working directory spelled `c:\` against `C:/`; builders create their own worktree with `git worktree add` under `.claude/worktrees/`.
- Challenge fix status (2026-11-13): merged U-51 (#113), U-52 (#108), U-56 (#109, took migration 0009 because it landed first), U-57 (#110), U-58 (#112), U-61 (#111). U-61 changed the conflict wording of U-35: when the other change came from the web the marks read "You typed X, the web now has Y" and the button "Keep the stored value"; "Keep Telegram's" remains for a Telegram change (AC-28). U-53 takes migration 0010 and U-54 migration 0011.
- Status of the round 2 and round 3 findings (2026-11-14, phase 8): SEC2-04 and SEC3-02 are one open item, the ingress controller decision (D-21); no unit fixes it, it is a gate before production in `docs/release/web-settings-prod.md` (HSTS, redirect, TLS minimum and the 8 KB body cap proven on the real ingress in staging). SEC2-06 (security events kept until the purge) is closed by U-49 (90 days) and U-71 (expired `web_notice_token`), with the residual that the purge runs only at deploy time (PreSync), tracked as a release condition (a sync at least every 30 days, SEC3-04). SEC2-09 (documents no longer match the build) and SEC3-07 (D-7 meant two things; D-7 is the certificate expiry alert, the ingress controller is D-21, D-20 is the round 3 moderator decision) are closed by the documentation unit U-72. RT2-07 (the web lock is observable) is closed by U-69. RT2-02 is accepted as R-4 (Marco, 2026-11-13). The other round 2 findings went into U-63 to U-67 and U-49, the round 3 findings into U-68 to U-71. SEC3-03, SEC3-05 and SEC3-06 (the cap wording of AC-29, the R1/R2 split of AC-20 and AC-21, the data classification, the ADR amendments and the README line on deletes) are corrected in the documentation PR `docs/INT-002/web-settings-finish`, which also does CR-06 (the user guide). Still open: CR-01 (the architecture check arrives with the kit 0.5.0 upgrade, PR #84), CR-08 (hand-written boundary validation in `apps/web`, Low), RT3-07 (no limiter total per /48, accepted as R-5) and the in-memory "spent" rule of the wrong-code alert, which is forgotten after an agent restart.
- Units: 72 are planned; U-45 to U-47 (R2) are not built and U-72 is this documentation unit.
