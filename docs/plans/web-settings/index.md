---
intent: INT-002
feature: web-settings
spec: docs/specs/web-settings.md
---

# Web settings (login and settings page)

Overview of the plan: what is built, in which order and what can run in parallel. A builder reads only its own unit file (linked in the table) plus this index when it needs the dependencies.

## Units

| Unit | Name | Layer | Depends on | Parallel | Wave |
|---|---|---|---|---|---|
| [U-web-settings-01](U-web-settings-01.md) | Pebble tokens, self-hosted fonts and contrast test (R1) | web | — | yes | 1 |
| [U-web-settings-02](U-web-settings-02.md) | Backend image with the shared package (R1) | infra | — | yes | 1 |
| [U-web-settings-03](U-web-settings-03.md) | Clock, IdSource, CodeSource, fakes and the canary log check (R1) | backend | U-web-settings-02 | no | 2 |
| [U-web-settings-04](U-web-settings-04.md) | Settings and start-up validation (R1) | backend | U-web-settings-03 | no | 3 |
| [U-web-settings-05](U-web-settings-05.md) | HTTP surface: errors, headers, request id, LimitGuard seam, route inventory (R1) | backend | U-web-settings-04 | no | 4 |
| [U-web-settings-06](U-web-settings-06.md) | Migration 0008: web_auth, web guard line, contract version, notice record (R1) | backend (database; agent migration chain) | — | yes | 1 |
| [U-web-settings-07](U-web-settings-07.md) | Grants for the web role and the agent's new rights (R1) | backend (database) | U-web-settings-06 | no | 2 |
| [U-web-settings-08](U-web-settings-08.md) | Migrate job creates the roles from a list; WEB_ROLE_PASSWORD everywhere (R1) | infra (database) | U-web-settings-07 | no | 3 |
| [U-web-settings-09](U-web-settings-09.md) | Database access, shared fixture and readiness (R1) | backend | U-web-settings-04, U-web-settings-06, U-web-settings-07 | no | 4 |
| [U-web-settings-10](U-web-settings-10.md) | Pure rules for the code: hash, mask, username digest, return path (R1) | backend (pure module; mutation-gated) | U-web-settings-02 | yes | 2 |
| [U-web-settings-11](U-web-settings-11.md) | Pure rules for time: code life, attempts, cooldown, hourly cap, session expiry (R1) | backend (pure module; mutation-gated) | U-web-settings-02 | yes | 2 |
| [U-web-settings-12](U-web-settings-12.md) | Mail sender port, SMTP adapter and fake (R1) | backend | U-web-settings-04 | yes | 4 |
| [U-web-settings-13](U-web-settings-13.md) | Security event store (R1; the alert is R2) | backend | U-web-settings-07, U-web-settings-09, U-web-settings-10 | no | 5 |
| [U-web-settings-14](U-web-settings-14.md) | Logging hygiene (R1) | backend | U-web-settings-05 | yes | 5 |
| [U-web-settings-15](U-web-settings-15.md) | Session store, cookie and lock check (R1) | backend | U-web-settings-05, U-web-settings-09, U-web-settings-11, U-web-settings-13 | no | 6 |
| [U-web-settings-16](U-web-settings-16.md) | Login request store (R1) | backend (database) | U-web-settings-07, U-web-settings-09, U-web-settings-10, U-web-settings-11 | yes | 5 |
| [U-web-settings-17](U-web-settings-17.md) | Request-code endpoint (R1) | backend | U-web-settings-05, U-web-settings-12, U-web-settings-13, U-web-settings-16 | no | 6 |
| [U-web-settings-18](U-web-settings-18.md) | Verify-code endpoint and sign-in (R1) | backend | U-web-settings-13, U-web-settings-15, U-web-settings-16 | no | 7 |
| [U-web-settings-19](U-web-settings-19.md) | CSRF, Origin, /api/session and logout (R1) | backend | U-web-settings-15 | no | 7 |
| [U-web-settings-20](U-web-settings-20.md) | Settings read: models, GET, RULES, field map, checked-in OpenAPI (R1) | backend | U-web-settings-05, U-web-settings-09, U-web-settings-15 | no | 7 |
| [U-web-settings-21](U-web-settings-21.md) | Settings write repository (R1) | backend (database) | U-web-settings-07, U-web-settings-09, U-web-settings-20 | no | 8 |
| [U-web-settings-22](U-web-settings-22.md) | Settings write route PUT (R1) | backend | U-web-settings-19, U-web-settings-21 | no | 9 |
| [U-web-settings-23](U-web-settings-23.md) | Places route (R1) | backend | U-web-settings-05, U-web-settings-15 | yes | 7 |
| [U-web-settings-24](U-web-settings-24.md) | In-process rate and body limits (R1; release gate) | backend (pure module; mutation-gated) | U-web-settings-05, U-web-settings-13, U-web-settings-17, U-web-settings-18 | yes | 8 |
| [U-web-settings-25](U-web-settings-25.md) | Walking skeleton at API level (M1) | backend | U-web-settings-18, U-web-settings-19, U-web-settings-22 | no | 10 |
| [U-web-settings-26](U-web-settings-26.md) | Web notices in the agent (R1; release gate) | agent | U-web-settings-06, U-web-settings-07 | yes | 3 |
| [U-web-settings-27](U-web-settings-27.md) | Notice buttons: Undo, Undo and lock, /web_unlock (R1; release gate) | agent | U-web-settings-26 | no | 4 |
| [U-web-settings-28](U-web-settings-28.md) | Web app shell, API client and session (R1) | web | U-web-settings-01, U-web-settings-20 | no | 8 |
| [U-web-settings-29](U-web-settings-29.md) | UI primitives: Button, Field, Banner, TimeField, Layout (R1) | web | U-web-settings-01 | yes | 2 |
| [U-web-settings-30](U-web-settings-30.md) | Login page: username step and code step (R1) | web | U-web-settings-28, U-web-settings-29, U-web-settings-17, U-web-settings-18 | yes | 9 |
| [U-web-settings-31](U-web-settings-31.md) | Login page: resend, countdown and refusal states (R1) | web | U-web-settings-30 | no | 10 |
| [U-web-settings-32](U-web-settings-32.md) | Settings form with slots: load, validate, save (R1) | web | U-web-settings-22, U-web-settings-28, U-web-settings-29 | yes | 10 |
| [U-web-settings-33](U-web-settings-33.md) | ZoneCombobox with live time (R1) | web | U-web-settings-23, U-web-settings-32 | no | 11 |
| [U-web-settings-34](U-web-settings-34.md) | Save feedback: last-change line, saved banner, zone preview (R1) | web | U-web-settings-32, U-web-settings-33 | yes | 12 |
| [U-web-settings-35](U-web-settings-35.md) | Conflict handling: Use mine and Keep Telegram's (R1) | web | U-web-settings-32 | yes | 11 |
| [U-web-settings-36](U-web-settings-36.md) | Accessibility and responsive states: Playwright ui-states (R1; release gate) | web | U-web-settings-30, U-web-settings-31, U-web-settings-32, U-web-settings-33, U-web-settings-34, U-web-settings-35 | no | 13 |
| [U-web-settings-37](U-web-settings-37.md) | Prod-like TLS edge and nginx exact routes (R1) | infra | U-web-settings-02 | yes | 2 |
| [U-web-settings-38](U-web-settings-38.md) | Prod-like mail catcher with STARTTLS and the api service (R1) | infra | U-web-settings-12, U-web-settings-37 | no | 5 |
| [U-web-settings-39](U-web-settings-39.md) | Prod-like TLS database (R1) | infra | U-web-settings-08, U-web-settings-09, U-web-settings-37 | yes | 5 |
| [U-web-settings-40](U-web-settings-40.md) | Chart: local ingress, TLS and exposed paths (R1) | infra | — | yes | 1 |
| [U-web-settings-41](U-web-settings-41.md) | Chart: NetworkPolicy, one replica, secrets and SMTP egress (R1; release gate) | infra | U-web-settings-08, U-web-settings-40 | no | 4 |
| [U-web-settings-42](U-web-settings-42.md) | One prod-like CI job, setup project and smoke test (R1; M2) | infra | U-web-settings-30, U-web-settings-32, U-web-settings-37, U-web-settings-38, U-web-settings-39 | no | 11 |
| [U-web-settings-43](U-web-settings-43.md) | Journey over the prod-like stack (R1; release gate) | web (end to end) | U-web-settings-33, U-web-settings-34, U-web-settings-35, U-web-settings-36, U-web-settings-42 | no | 14 |
| [U-web-settings-44](U-web-settings-44.md) | Mutation workflow wiring for the pure security modules (R1; release gate) | infra | U-web-settings-10, U-web-settings-11, U-web-settings-24 | yes | 9 |
| [U-web-settings-45](U-web-settings-45.md) | Reset to defaults: backend (R2) | backend | U-web-settings-22 | yes | 10 |
| [U-web-settings-46](U-web-settings-46.md) | Reset to defaults: web (R2) | web | U-web-settings-32, U-web-settings-45 | no | 11 |
| [U-web-settings-47](U-web-settings-47.md) | Typed values kept across session expiry (R2) | web | U-web-settings-30, U-web-settings-32 | yes | 11 |
| [U-web-settings-48](U-web-settings-48.md) | Telegram alert after 5 wrong or expired codes (R1 since ADR-0039) | agent | U-web-settings-13, U-web-settings-26 | yes | 6 |
| [U-web-settings-49](U-web-settings-49.md) | Audit retention purge in the migrate job (R1 since 2026-11-13) | backend (database; agent image) | U-web-settings-07, U-web-settings-08 | yes | 4 |
| [U-web-settings-50](U-web-settings-50.md) | Decoy login requests for unknown usernames (R1; release gate; ADR-0038) | backend | U-web-settings-17, U-web-settings-18, U-web-settings-24 | no | 9 |
| [U-web-settings-51](U-web-settings-51.md) | Limits before the session lookup, IPv6 per /64, bounded counters (R1; challenge fix; RT-03, RT-05, SEC-06) | backend | U-web-settings-24 | yes | 9 |
| [U-web-settings-52](U-web-settings-52.md) | Chart sets the trusted proxies; production refuses an empty list (R1; challenge fix; RT-02, SEC-01) | infra, backend | U-web-settings-41 | yes | 5 |
| [U-web-settings-53](U-web-settings-53.md) | The owner cannot be locked out by decoys, other clients or the cap (R1; challenge fix; ADR-0039; RT-01, RT-04, RT-06, SEC-02) | backend, database (migration 0010) | U-web-settings-50, U-web-settings-51 | no | 10 |
| [U-web-settings-54](U-web-settings-54.md) | Wrong codes are counted, the lock stops code mail, the mail text says what to do (R1; challenge fix; ADR-0039; RT-09, SEC-04, SEC-08, SEC-09) | backend, database (migration 0011) | U-web-settings-53 | no | 11 |
| [U-web-settings-55](U-web-settings-55.md) | Agent sets the web lock after repeated wrong codes (R1; challenge fix; ADR-0039; RT-07, SEC-03) | agent | U-web-settings-48, U-web-settings-54 | no | 12 |
| [U-web-settings-56](U-web-settings-56.md) | Undo burst is identified by an explicit id (R1; challenge fix; CR-07) | agent, database (migration 0009) | U-web-settings-27 | yes | 5 |
| [U-web-settings-57](U-web-settings-57.md) | Ingress gates: HSTS, certificate alert, image digests (R1; challenge fix; RT-10, SEC-05, SEC-07) | infra | U-web-settings-41 | yes | 5 |
| [U-web-settings-58](U-web-settings-58.md) | TLS with verify-full for the agent and the migrate job (R1; challenge fix; SEC-10) | infra, agent | U-web-settings-39 | yes | 6 |
| [U-web-settings-59](U-web-settings-59.md) | Safe defaults and response headers (R1; challenge fix; SEC-11, SEC-12, CR-09, CR-11) | backend, web (nginx) | U-web-settings-52 | no | 6 |
| [U-web-settings-60](U-web-settings-60.md) | One cookie builder, current attemptsLeft docs, one retention constant (R1; challenge fix; CR-03, CR-04, CR-10) | backend | U-web-settings-53, U-web-settings-54 | no | 12 |
| [U-web-settings-61](U-web-settings-61.md) | Conflict marks name where the other change came from (R1; challenge fix; RT-08) | web | U-web-settings-35 | yes | 12 |
| [U-web-settings-62](U-web-settings-62.md) | Test hygiene: no silent skips, structural decoy check (R1; challenge fix; CR-02, CR-05, CR-12) | backend, web tests | U-web-settings-53 | no | 11 |
| [U-web-settings-63](U-web-settings-63.md) | The lock counts only wrong codes against a live request (R1; challenge round 2; ADR-0039 amendment; SEC2-01, RT2-01) | backend (agent unchanged) | U-web-settings-54 | yes | 12 |
| [U-web-settings-64](U-web-settings-64.md) | A full decoy class is invisible, replace by cookie only, limiter keeps room for the owner (R1; challenge round 2; RT2-03, RT2-04, RT2-05) | backend | U-web-settings-53, U-web-settings-51 | yes | 11 |
| [U-web-settings-65](U-web-settings-65.md) | Contract version, count integrity, column grants, event index (R1; challenge round 2; SEC2-02, SEC2-03, RT2-06, RT2-09) | database (migration 0012), backend, agent | U-web-settings-54, U-web-settings-48 | yes | 12 |
| [U-web-settings-66](U-web-settings-66.md) | Chart: environment cannot be overridden, digests everywhere (R1; challenge round 2; RT2-08, SEC2-05) | infra | U-web-settings-57, U-web-settings-58 | yes | 7 |
| [U-web-settings-67](U-web-settings-67.md) | Digest domain separation, IPv6 event class (R1; challenge round 2; SEC2-07, SEC2-08) | backend | U-web-settings-64, U-web-settings-63 | no | 13 |
| [U-web-settings-68](U-web-settings-68.md) | The lock counts only wrong codes against the owner's real requests; an expired request dies on its first post (R1; challenge round 3; ADR-0039 amendment 2; RT3-01, RT3-04, SEC3-01) | backend | U-web-settings-63, U-web-settings-67 | no | 14 |
| [U-web-settings-69](U-web-settings-69.md) | No swallowed decoys, and the lock leaves no trace (R1; challenge round 3; ADR-0039 amendment 2; RT3-02, RT3-03) | backend | U-web-settings-68 | no | 15 |
| [U-web-settings-70](U-web-settings-70.md) | Chart: case-insensitive env guards, pinned test image, a disruption budget that allows one eviction (R1; challenge round 3; RT3-06, RT3-08, SEC3-08) | infra | U-web-settings-66 | yes | 8 |
| [U-web-settings-71](U-web-settings-71.md) | The web role cannot forge security events; expired notice tokens are purged (R1; challenge round 3; RT3-05, SEC3-04) | database (migration 0013), agent | U-web-settings-65, U-web-settings-49 | yes | 13 |
| [U-web-settings-73](U-web-settings-73.md) | The local week-test stack: the whole feature in Docker with the real limits (R1; test environment; D-22) | infra, tooling | U-web-settings-58, U-web-settings-66, U-web-settings-39 | yes | 8 |
| [U-web-settings-74](U-web-settings-74.md) | Production prepared, not deployed (R1; no rollout; D-21) | infra | U-web-settings-57, U-web-settings-66, U-web-settings-70 | yes | 9 |
| [U-web-settings-75](U-web-settings-75.md) | The local stack supplies a missing runtime password itself (R1; test environment; D-22) | tooling | U-web-settings-73 | yes | 9 |
| [U-web-settings-76](U-web-settings-76.md) | The Gmail consent runs in the agent container for the local stack (R1; test environment; D-23) | infra, tooling, agent | U-web-settings-73, U-web-settings-75 | yes | 10 |
| [U-web-settings-77](U-web-settings-77.md) | The sign-in username ignores surrounding spaces and letter case (R1; backend; D-24) | backend | U-web-settings-17, U-web-settings-18, U-web-settings-50 | yes | 10 |
| [U-web-settings-78](U-web-settings-78.md) | The login page says it wants the username, not the e-mail address (R1; D-22) | web | U-web-settings-31 | yes | 11 |

## Build order

1. Wave 1 — in parallel: U-web-settings-01, U-web-settings-02, U-web-settings-06, U-web-settings-40
2. Wave 2 (after wave 1) — in parallel: U-web-settings-10, U-web-settings-11, U-web-settings-29, U-web-settings-37; one at a time: U-web-settings-03, U-web-settings-07
3. Wave 3 (after wave 2) — in parallel: U-web-settings-26; one at a time: U-web-settings-04, U-web-settings-08
4. Wave 4 (after wave 3) — in parallel: U-web-settings-12, U-web-settings-49; one at a time: U-web-settings-05, U-web-settings-09, U-web-settings-27, U-web-settings-41
5. Wave 5 (after wave 4) — in parallel: U-web-settings-14, U-web-settings-16, U-web-settings-39, U-web-settings-52, U-web-settings-56, U-web-settings-57; one at a time: U-web-settings-13, U-web-settings-38
6. Wave 6 (after wave 5) — in parallel: U-web-settings-48, U-web-settings-58; one at a time: U-web-settings-15, U-web-settings-17, U-web-settings-59
7. Wave 7 (after wave 6) — in parallel: U-web-settings-23, U-web-settings-66; one at a time: U-web-settings-18, U-web-settings-19, U-web-settings-20
8. Wave 8 (after wave 7) — in parallel: U-web-settings-24, U-web-settings-70, U-web-settings-73; one at a time: U-web-settings-21, U-web-settings-28
9. Wave 9 (after wave 8) — in parallel: U-web-settings-30, U-web-settings-44, U-web-settings-51, U-web-settings-74, U-web-settings-75; one at a time: U-web-settings-22, U-web-settings-50
10. Wave 10 (after wave 9) — in parallel: U-web-settings-32, U-web-settings-45, U-web-settings-76, U-web-settings-77; one at a time: U-web-settings-25, U-web-settings-31, U-web-settings-53
11. Wave 11 (after wave 10) — in parallel: U-web-settings-35, U-web-settings-47, U-web-settings-64, U-web-settings-78; one at a time: U-web-settings-33, U-web-settings-42, U-web-settings-46, U-web-settings-54, U-web-settings-62
12. Wave 12 (after wave 11) — in parallel: U-web-settings-34, U-web-settings-61, U-web-settings-63, U-web-settings-65; one at a time: U-web-settings-55, U-web-settings-60
13. Wave 13 (after wave 12) — in parallel: U-web-settings-71; one at a time: U-web-settings-36, U-web-settings-67
14. Wave 14 (after wave 13) — one at a time: U-web-settings-43, U-web-settings-68
15. Wave 15 (after wave 14) — one at a time: U-web-settings-69

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
- The R1 build exposes no R2 surface: U-05 (no `/api/settings/reset` in the route inventory and in `openapi.json`), U-32 (no Reset button in the DOM) and U-43 (the path answers 404 through the edge). U-45 and U-46 add them together with their tests. U-45 (backend and edge side) flipped U-05, U-22 and U-43: the path is on the allow-list and in `openapi.json`, and through the edge GET answers 405 and an unauthenticated POST answers 401; the web side (U-32) is flipped by U-46 (the no-Reset assertion of `SettingsPage.test.tsx` now checks that the button is there and the dialog is closed).

## Units with a suffixed id (not split into files)

## Coverage of the acceptance criteria

| AC | Units |
| --- | --- |
| AC-1 | 20, 25, 32, 34, 42, 43 |
| AC-2 | 15, 20, 22, 23, 28, 43 |
| AC-3 | 10, 11, 16, 18, 25, 30, 31, 42, 43, 50, 60, 77 |
| AC-4 | 04, 38 |
| AC-5 | 11, 16, 17, 18, 31 |
| AC-6 | 10, 18, 30, 77 |
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
| AC-30 | 17, 30, 50, 53, 62, 63, 64, 68, 69, 77 |
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
- D-21 the ingress controller is Traefik (ADR-0040, Marco agreed 2026-11-14);  HSTS, redirect and TLS minimum are a gate before production (round 3, SEC3-02, formerly mixed up with D-7 which is the certificate expiry alert).
- D-23 the Gmail consent runs in the agent container for the local stack (Marco, 2026-11-14).
- D-22 the feature is tested for a week in Docker before any production step: the stack runs from the main checkout under the project name `mail-assistant`, reachable from this computer only, with the real limits (U-73); production is prepared, not deployed (U-74) (Marco, 2026-11-14).
- D-24 the username is compared without surrounding spaces and without letter case; the page says it wants the username, not the e-mail address (Marco, 2026-11-14; U-77, U-78).
- D-13 unknown usernames get a decoy login request and `attemptsLeft` is shown every time (Marco, 2026-11-12; ADR-0038; U-50). This replaces the earlier rule "`attemptsLeft` only for a live login request".
- Fixed inside the units: cookie lifetimes (`__Host-login` Max-Age 600, `__Host-session` Max-Age 43200), HSTS without `includeSubDomains`, the SMTP library (`aiosmtplib`), and `attemptsLeft` in the generic verify failure body for any login request cookie, real or decoy (D-13).

## Open points

- Hosting (ADR-0012, ADR-0037): the local host name, the cluster and the ingress controller are decided before staging. The build and all tests run against the prod-like stack and do not wait. The controller-specific ingress settings (8 KB body cap, TLS minimum, log format without the query string) are per-environment values (U-40); the pinned log format is settled with the controller.
- The agent run interval for the page text: `noticeIntervalMinutes` is set from one chart value that the worker chart also uses (`POLL_INTERVAL_SECONDS` is 60 in compose); the production value is set when the cluster values exist.
- Two-step verification on Marco's mailbox is a condition for production (R-1); R-1 is reviewed on 2027-05-10. R-2 (anything on the local network can reach the login page) is bounded by U-24 and U-16.
- The agent is not in the prod-like stack, so web notices, Undo and the lock are tested at agent level with a real database (U-26, U-27), and the api side of the lock in U-15, U-18 and U-43. A full chain test across both belongs to staging.
- Documentation (phase 8) is not a unit here: the user-guide page for the settings page with screenshots, the API guide and the generated reference are written from what is built.
- Total: 78 units (75 in R1, 3 in R2 (U-45, U-46, U-47: built 2026-11-14); U-73 to U-78 added 2026-11-14; U-68 to U-72 come from challenge round 3; U-49 moved into R1 as well and U-63 to U-67 come from challenge round 2; U-48 moved into R1 and U-51 to U-62 are challenge fixes), above the target of about 35 and the later ceiling of about 40. The excess comes from the QA splits (clock and code source, security events and logging hygiene, the TLS edge, the TLS database and the mail catcher, CI sequence and journey) and the sign-in units the e-mailed code adds (code rules, mail sender, login request store, two endpoints, two login-page units). Merge candidates if fewer are wanted: U-10 with U-11, U-30 with U-31, U-40 with U-41, U-13 with U-14, U-25 with U-22; each merge costs single responsibility.

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
- Ingress-controller vocabulary: the values and tests spoke ingress-nginx while kind runs Traefik; U-74 rebuilt the ingress as Traefik objects (ADR-0040). Open before staging: the api PodDisruptionBudget default `minAvailable: 1` with one replica.
- Tooling: the worktree isolation of the Agent tool refuses a primary working directory spelled `c:\` against `C:/`; builders create their own worktree with `git worktree add` under `.claude/worktrees/`.
- Challenge fix status (2026-11-13): merged U-51 (#113), U-52 (#108), U-56 (#109, took migration 0009 because it landed first), U-57 (#110), U-58 (#112), U-61 (#111). U-61 changed the conflict wording of U-35: when the other change came from the web the marks read "You typed X, the web now has Y" and the button "Keep the stored value"; "Keep Telegram's" remains for a Telegram change (AC-28). U-53 takes migration 0010 and U-54 migration 0011.
- Status of the round 2 and round 3 findings (2026-11-14, phase 8): SEC2-04 and SEC3-02 are one open item, the ingress controller decision (D-21); no unit fixes it, it is a gate before production in `docs/release/web-settings-prod.md` (HSTS, redirect, TLS minimum and the 8 KB body cap proven on the real ingress in staging). SEC2-06 (security events kept until the purge) is closed by U-49 (90 days) and U-71 (expired `web_notice_token`), with the residual that the purge runs only at deploy time (PreSync), tracked as a release condition (a sync at least every 30 days, SEC3-04). SEC2-09 (documents no longer match the build) and SEC3-07 (D-7 meant two things; D-7 is the certificate expiry alert, the ingress controller is D-21, D-20 is the round 3 moderator decision) are closed by the documentation unit U-72. RT2-07 (the web lock is observable) is closed by U-69. RT2-02 is accepted as R-4 (Marco, 2026-11-13). The other round 2 findings went into U-63 to U-67 and U-49, the round 3 findings into U-68 to U-71. SEC3-03, SEC3-05 and SEC3-06 (the cap wording of AC-29, the R1/R2 split of AC-20 and AC-21, the data classification, the ADR amendments and the README line on deletes) are corrected in the documentation PR `docs/INT-002/web-settings-finish`, which also does CR-06 (the user guide). Still open: CR-01 (the architecture check arrives with the kit 0.5.0 upgrade, PR #84), CR-08 (hand-written boundary validation in `apps/web`, Low), RT3-07 (no limiter total per /48, accepted as R-5) and the in-memory "spent" rule of the wrong-code alert, which is forgotten after an agent restart.
- 2026-11-14, added after the review: R2 is built and merged (U-45 the reset route in #136, U-47 the kept typed values in #135, U-46 the Reset to defaults button in #138). The local week-test stack (U-73 in #137, U-75 in #140, U-76 in #143), production prepared for Traefik without a rollout (U-74 in #141, ADR-0040), the username comparison without spaces and letter case (U-77 in #144) and the login page hint (U-78 in #142) were added. Nothing is deployed to production.
- Units: 78 in total, counted as the 77 `### U-web-settings-` headings (U-72 has none) plus the documentation unit U-72. U-45 to U-47 (R2) are built; U-72 is this documentation unit.
