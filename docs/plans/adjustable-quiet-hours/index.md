---
intent: INT-002
feature: adjustable-quiet-hours
spec: docs/specs/adjustable-quiet-hours.md
---

# adjustable-quiet-hours

Overview of the plan: what is built, in which order and what can run in parallel. A builder reads only its own unit file (linked in the table) plus this index when it needs the dependencies.

## Units

| Unit | Name | Layer | Depends on | Parallel | Wave |
|---|---|---|---|---|---|
| [U-quiet-hours-01](U-quiet-hours-01.md) | Schedule policy, validation and time parsing | backend (shared package) | — | yes | 1 |
| [U-quiet-hours-02](U-quiet-hours-02.md) | Place list and lookup | backend (shared package) | — | yes | 1 |
| [U-quiet-hours-03](U-quiet-hours-03.md) | Rebuild time_policy on TimePolicy (core and callers, one PR) | backend | U-quiet-hours-01b | no | 1 |
| [U-quiet-hours-04](U-quiet-hours-04.md) | Migration 0004: settings schema, trigger, constraints | backend (database) | — | yes | 1 |
| [U-quiet-hours-05](U-quiet-hours-05.md) | Settings store | integration (testcontainers PostgreSQL, `tests/db/conftest.py`) and contract | U-quiet-hours-01, U-quiet-hours-04 | no | 2 |
| [U-quiet-hours-07](U-quiet-hours-07.md) | Router registry, tokens and expiry | backend | U-quiet-hours-06a | no | 1 |
| [U-quiet-hours-08](U-quiet-hours-08.md) | PolicySource with fallback and notice | integration (testcontainers PostgreSQL) with a fake slow port and `FakeClock` | U-quiet-hours-01, U-quiet-hours-05 | no | 3 |
| [U-quiet-hours-09](U-quiet-hours-09.md) | Settings dialogue: card, times, quiet hours, conflicts | backend | U-quiet-hours-01, U-quiet-hours-05, U-quiet-hours-07 | yes | 3 |
| [U-quiet-hours-10](U-quiet-hours-10.md) | Zone dialogue | backend | U-quiet-hours-02, U-quiet-hours-09 | no | 4 |
| [U-quiet-hours-11](U-quiet-hours-11.md) | Confirmation and Undo | backend | U-quiet-hours-10 | no | 5 |
| [U-quiet-hours-12](U-quiet-hours-12.md) | Policy snapshot in delivery, snooze and triage | backend | U-quiet-hours-03, U-quiet-hours-04, U-quiet-hours-06a, U-quiet-hours-08 | yes | 4 |
| [U-quiet-hours-13](U-quiet-hours-13.md) | Overview window across zone changes | backend | U-quiet-hours-03, U-quiet-hours-08 | yes | 4 |
| [U-quiet-hours-14](U-quiet-hours-14.md) | Wiring and end-to-end | backend | U-quiet-hours-06b, U-quiet-hours-11, U-quiet-hours-12, U-quiet-hours-13 | no | 6 |

## Build order

1. Wave 1 — in parallel: U-quiet-hours-01, U-quiet-hours-02, U-quiet-hours-04; one at a time: U-quiet-hours-03, U-quiet-hours-07
2. Wave 2 (after wave 1) — one at a time: U-quiet-hours-05
3. Wave 3 (after wave 2) — in parallel: U-quiet-hours-09; one at a time: U-quiet-hours-08
4. Wave 4 (after wave 3) — in parallel: U-quiet-hours-12, U-quiet-hours-13; one at a time: U-quiet-hours-10
5. Wave 5 (after wave 4) — one at a time: U-quiet-hours-11
6. Wave 6 (after wave 5) — one at a time: U-quiet-hours-14

Code lives in `agents/mail-triage` (Python) and in the new shared package `packages/schedule-policy` (pure Python). No UI. Each unit gets its own git worktree and branch `feat/INT-002/adjustable-quiet-hours/<nn>` and is built test-first: a failing test is shown before the implementation. A test is named after its criterion: `test_given_<x>_when_<y>_then_<z>`. Commits carry `Refs: INT-002` and `Unit: U-quiet-hours-<nn>`.

Common guardrails for every unit: `guardrail-python`, `guardrail-pytest`. Others are listed per unit.

Test rules from the round table and the plan review: `now` and a `FakeClock` are passed in (never `datetime.now()`); no real Telegram, Google or network; real PostgreSQL (testcontainers, as in `tests/db/conftest.py`) for the settings tables; `tzdata` pinned; a canary zone `Pacific/Kiritimati` that must never appear in captured logs (one shared check in `tests/conftest.py`); `make_policy` and `FakeClock` come from `schedule_policy/testing.py` (U-01).

Plan review: the QA strategist reviewed this plan on 2026-11-09 (10 findings, 3 blockers). The build-green order, the unit sizes, the thin criteria and the test layers below are the result.

## Order and parallelism

```text
U-01 policy + validation + parsing ─► U-01b wire the package into the agent (uv, Docker, CI) ─► U-03 rebuild time_policy + callers (DST)
U-02 place list + lookup ──────────────────────────────────────────────────────────────────────────────────────────► U-10 zone dialogue
U-04 migration 0004 ─┬─► U-05 settings store ─► U-08 PolicySource ─┬─► U-12 policy in delivery / snooze / triage
                     │                                              └─► U-13 overview window
                     └─► U-06a conversation store (column stays) ─► U-07 router, tokens, expiry ─┬─► U-06b migration 0005 drops awaiting_input
                                                                                                  └─► U-09 dialogue ─► U-10 zone ─► U-11 confirm + undo
U-12, U-13, U-06b, U-11 ─► U-14 wiring + end-to-end ─► U-15a owner role + migration job ─► U-15b role and image checks
```

Build-green rules: every unit merges with the full existing suite green. U-03 changes `time_policy` and all its callers in one branch (two units, one PR). `alert.awaiting_input` is dropped only in U-06b, after U-07 removes the last reader. The shared package is wired into the agent (lockfile, image build, CI) in U-01b, before any code imports it.

U-01, U-02 and U-04 share no files and run in parallel. U-12 runs after U-06a (both change `snooze.py` and `pg_store.py`); U-12 and U-13 can run in parallel. U-09, U-10 and U-11 share `settings_dialog.py` and `settings_text.py` and run one after the other.

## Units with a suffixed id (not split into files)

### U-quiet-hours-01b: Wire the shared package into the agent

- Layer: infra
- Contract: `agents/mail-triage` depends on `packages/schedule-policy` (uv path dependency, lockfile updated); pytest imports it; the agent image is built from the repo root and contains it; CI builds and tests with it.
- Files: `agents/mail-triage/pyproject.toml`, `agents/mail-triage/uv.lock`, `agents/mail-triage/Dockerfile`, `.github/workflows/` (build context), `docker-compose.yml` (build context)
- Depends on: U-quiet-hours-01
- Parallel: no
- Guardrails: guardrail-docker, guardrail-compose
- Criteria:
  1. Given a clean `uv sync` in `agents/mail-triage`, When `import schedule_policy` runs, Then it works (type: happy).
  2. Given a docker build from the repo root, When the image starts, Then `import schedule_policy` works and the image scan has no new High or Critical finding (type: security).
  3. Given the existing agent suite, When run, Then it is green (type: happy).

### U-quiet-hours-06a: Conversation store and move of snooze and reply

- Layer: backend
- Contract: `ConversationStore.start(kind, target, step, partial, ttl)`, `current()`, `advance(...)`, `clear()`; one row; random nonce; expiry. `SnoozeService`, `ReplyService` and the router's `RouterStore.set_awaiting`/`awaiting` use it instead of `alert.awaiting_input`. The column stays until U-06b.
- Files: `app/db/pg_conversation.py`, `app/db/pg_store.py`, `app/usecases/dispatch.py` (adapter swap only), `app/usecases/snooze.py`, `app/usecases/reply.py`, `tests/usecases/test_dispatch.py`, `tests/usecases/test_snooze.py`, `tests/usecases/test_reply.py`, `tests/db/test_pg_store.py`
- Depends on: U-quiet-hours-04
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the existing snooze and reply tests, When run on the conversation store, Then they pass unchanged (type: happy).
  2. Given a pending snooze question, When a reply question starts, Then only the reply is pending (type: edge).
  3. Given a restart of the agent, When a question is pending, Then it is still pending until it expires (type: edge).
  4. Given snooze and reply questions, When they have no expiry set, Then their behaviour is unchanged (C-8) (type: happy).
  5. Given the full existing suite (test_dispatch, test_pg_store, test_snooze, test_reply, persistence), When run on the conversation store, Then it is green (type: happy).

### U-quiet-hours-06b: Drop alert.awaiting_input

- Layer: backend (database)
- Contract: migration 0005 moves any open question to the conversation row and drops `alert.awaiting_input`; downgrade restores the column.
- Files: `migrations/versions/0005_drop_awaiting_input.py`, `app/db/models.py`, `tests/db/test_migrate.py`
- Depends on: U-quiet-hours-07
- Parallel: yes (with U-09)
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given revision 0004 with a pending question, When 0005 runs, Then it is moved to the conversation row and the column is gone (type: happy).
  2. Given 0005 with a pending question and data, When downgraded and upgraded again, Then nothing is lost (type: edge).
  3. Given a search of `app/` for `awaiting_input`, When run, Then there is no hit (type: happy).
  4. Given a fresh database, When all migrations run, Then the models match the schema (type: happy).

### U-quiet-hours-15a: Deployment: owner role and migration job

- Layer: infra
- Contract: a migration job with owner credentials (`database_owner_url`, a Kubernetes secret) and a runtime role that owns nothing, with the grants of `app/db/grants.sql`; compose and Helm values updated.
- Files: `deploy/` charts and values, `docker-compose.yml`, `app/settings.py`
- Depends on: U-quiet-hours-14
- Parallel: no
- Guardrails: guardrail-docker, guardrail-compose, guardrail-kubernetes, guardrail-helm
- Criteria:
  1. Given `helm lint` and the chart tests, When run, Then green with the migration job and its secret (type: happy).
  2. Given the prod-like compose profile, When started, Then the job migrates under the owner role and the agent runs under the runtime role (type: happy).
  3. Given a missing `database_owner_url`, When the migration job starts, Then it fails and names the key, not the value (type: error).
  4. Given the owner secret, When the manifests are checked, Then it is not in values files or logs (type: security).

### U-quiet-hours-15b: Role and image checks in the running stack

- Layer: infra
- Contract: checks in the prod-like stack that the runtime role cannot do DDL or change audit rows, and that the new image passes the scan.
- Files: prod-like check scripts under `tests/e2e/`, `.github/workflows/`
- Depends on: U-quiet-hours-15a
- Parallel: no
- Guardrails: guardrail-docker, guardrail-kubernetes
- Criteria:
  1. Given the runtime role in the running stack, When it tries DDL or deleting audit rows, Then refused (AC-30) (type: security).
  2. Given a Trivy scan of the new image, When run, Then no new High or Critical finding (type: security).

## Fixes from the challenge round (phase 6, ADR-0030)

Order: 16a, 16b, 16c, 16e and 16f are independent (different files) and run in parallel; 16d follows 16a. Source of each finding: RT = red-team, CR = code review, SEC = security review.

### U-quiet-hours-16a: Least-privilege grants and a server-derived audit actor

- Layer: backend
- Contract: new migration 0006 (0005 was taken by U-06b) and `grants.sql`: per-table grants; a trigger that enforces `version = old.version + 1`, derives `updated_via` from `session_user` and stores `session_user` in `settings_change` (ADR-0030 items 1 and 2).
- Files: `app/db/grants.sql`, `migrations/versions/0006_settings_guard.py`, `tests/db/test_settings_grants.py`, `tests/db/test_settings_migration.py`, `tests/e2e/test_runtime_role.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the runtime role, When it runs `update audit_log …` or `delete from audit_log`, `oauth_token`, `mail_item`, `alert`, `draft`, `poll_state`, `catchup_state` or `overview_log`, Then PostgreSQL refuses with 42501 (SEC-1, RT-3) (type: security).
  2. Given the runtime role, When it inserts into `audit_log`, upserts `oauth_token`/`poll_state`/`catchup_state`, updates `mail_item`/`alert`/`draft` and deletes from `conversation`, Then each works (type: happy).
  3. Given the runtime role, When it updates `settings.schedule` without raising the version by exactly one, Then the update is refused (RT-3) (type: security).
  4. Given the runtime role, When it writes `updated_via = 'web'`, Then the write is refused, and a `telegram` write records `session_user = 'mail_triage_runtime'` (SEC-4, RT-3) (type: security).
  5. Given settings written before the migration, When 0006 runs, Then existing rows and audit records stay valid and the upgrade and downgrade round-trip (type: edge).

### U-quiet-hours-16b: Hardened runtime-role setup in the migration job

- Layer: backend
- Contract: `migrate._connect` passes the TLS parameters of the owner URL; `_ensure_runtime_role` sends a client-computed SCRAM-SHA-256 verifier, `NOREPLICATION NOBYPASSRLS`, and the job fails (exit 6) when the runtime role has any role membership; `app.consent` no longer migrates (ADR-0030 item 3, SEC-2, SEC-5, RT-2).
- Files: `app/db/migrate.py`, `app/db/scram.py`, `app/consent.py`, `app/wiring.py` (message only), `tests/db/`, `tests/unit/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the SCRAM helper and the RFC 7677 test vector, When the verifier is computed, Then it equals the expected value (type: happy).
  2. Given a real PostgreSQL, When the job sets the password, Then the agent logs in with the clear password over SCRAM and no statement the server received contains it (RT-2, SEC-2) (type: security).
  3. Given `DATABASE_OWNER_URL=…?ssl=verify-full`, When the job connects, Then `asyncpg.connect` receives the TLS setting (RT-2) (type: security).
  4. Given a runtime role that has REPLICATION or a role membership, When the job runs, Then it resets REPLICATION and fails with exit 6 on the membership, naming the role, not the password (SEC-2) (type: error).
  5. Given a schema behind head, When `app.consent` runs, Then it exits naming the migrate job and runs no DDL (SEC-5) (type: error).

### U-quiet-hours-16c: `/settings` repairs an invalid stored row; one clock; cleanup

- Layer: backend
- Contract: the settings dialogue shows the values in use with a note when the stored row is invalid and lets a valid answer overwrite it (RT-1); `PgStore` receives the one `ConversationStore` (CR-2); stale docstring, dead `is_movable`, duplicate `_hhmm`, unreachable `except PolicyRefused` removed or covered (CR-3, CR-4, CR-5).
- Files: `app/usecases/settings_dialog.py`, `app/db/pg_settings_store.py`, `app/db/pg_store.py`, `app/wiring.py`, `app/settings.py`, `app/core/settings_text.py`, `app/usecases/policy_notice.py`, `pyproject.toml` (drop `httpx2`), tests
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-telegram, guardrail-pytest
- Criteria:
  1. Given a store whose `read()` raises `StoredSettingsInvalid`, When the allowed user sends `/settings`, Then no exception escapes and a card with the values in use and a note that the saved settings are invalid is sent (RT-1) (type: error).
  2. Given that card, When the user gives a valid answer and confirms, Then a whole new row is written over the invalid one at its version (RT-1) (type: happy).
  3. Given `build_runner` with a fake clock, When a snooze question is stored through `PgStore` and the router reads it, Then both judge expiry with the same clock (CR-2) (type: edge).
  4. Given the repository, When vulture runs on `app`, Then it reports no `is_movable` and `_hhmm` has one meaning (CR-4, CR-5) (type: happy).
  5. Given `httpx2`, When the dependency check runs, Then it is not in the dev dependencies (type: happy).

### U-quiet-hours-16d: Replayed Telegram updates are ignored after a restart

- Layer: backend
- Contract: the last handled `update_id` is stored in the database in a new column `poll_state.telegram_update_id` (migration 0007; the existing grant on `poll_state` is enough), right after a successful handling in its own transaction, and updates at or below it are skipped at start-up (RT-5).
- Files: `app/usecases/dispatch.py`, `app/adapters/telegram_inbox.py`, `app/runner.py`, `app/db/`, tests
- Depends on: U-quiet-hours-16a (migration order and grants)
- Parallel: no
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a start time answered by update 777 and a restart, When update 777 is delivered again, Then the router ignores it and sends nothing (RT-5) (type: security).
  2. Given a stored update id, When the agent starts, Then polling continues at that id plus one (type: happy).
  3. Given a failed handling step, When the agent restarts, Then the update is handled again, not lost (type: edge).

### U-quiet-hours-16e: Migrate Job: policy before the Job, own ServiceAccount, sealing by stdin, tzdata

- Layer: infra
- Contract: the migrate NetworkPolicy carries the same hook annotations as the Job with a lower weight and sync-wave; the Job has its own ServiceAccount with `automountServiceAccountToken: false`; the README seals by standard input (no `--from-literal` for secret keys); the runtime image uses the pinned `tzdata` package and not a system copy (RT-4, SEC-7, RT lead on tzdata).
- Files: `deploy/charts/worker/templates/migration.yaml`, `deploy/charts/worker/README.md`, `agents/mail-triage/Dockerfile`, `agents/mail-triage/tests/infra/test_deploy.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-docker
- Criteria:
  1. Given the rendered chart, When the migrate NetworkPolicy is read, Then it has the hook annotations of the Job and a lower weight and sync-wave (RT-4) (type: security).
  2. Given the rendered Job, When read, Then `serviceAccountName` is the chart's own and the token is not mounted (SEC-7) (type: security).
  3. Given the README, When checked, Then no `--from-literal=` is used for secret keys (SEC-7) (type: security).
  4. Given the image build, When `zoneinfo` resolves a zone, Then the data comes from the pinned `tzdata` wheel, checked by a test that fails when `/usr/share/zoneinfo` would win (type: edge).

### U-quiet-hours-16f: CI for the shared package and the mutation gate

- Layer: infra
- Contract: a CI job runs lint, type check, tests and `pip-audit` in `packages/schedule-policy`; a scheduled and manually startable workflow runs cosmic-ray for the agent and the package and fails below 85 % (ADR-0030 item 4, SEC-3, CR-1).
- Files: `.github/workflows/ci.yml`, `.github/workflows/mutation.yml`, `agents/mail-triage/tests/infra/test_deploy.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given `ci.yml`, When read, Then a job runs the package's tests and `pip-audit` (SEC-3) (type: security).
  2. Given `mutation.yml`, When read, Then it triggers on `schedule` and `workflow_dispatch`, runs both cosmic-ray configs and fails when the score is below 85 % (CR-1) (type: happy).
  3. Given a package change that breaks the 65-character time input limit, When CI runs, Then the package job fails (SEC-3) (type: security).

Built differently from the plan:

- 16a: migration `0006_settings_guard` (not 0005); refusals of the guard raise SQLSTATE 42501; the owner and other unmapped roles keep the channel they claim.
- 16d: migration `0007_telegram_update_id`. The id is stored after handling, not in the same transaction as the handling (handling spans several ports and the Telegram API), so a crash between the two replays one update once. A command that fails is retried and given up after 3 attempts, so one poison update cannot block the rest.
- 16f: the package job also found that `validate` accepted the zone `localtime` on a Linux host; the valid zones now come from the pinned `tzdata` package, not from `zoneinfo.available_timezones()`.
- Mutation scores (CI, Linux, CPython 3.14.4): first manual run 42865370873 gave `schedule_policy` 86.93 % and `time_policy.py` 89.83 % killed; after units 16g and 16h (tests only) `schedule_policy` is at 90.15 % and `time_policy.py` at 90.40 % (run 42883754433 on main), a margin of at least 5 points over the 85 % criteria. Most remaining survivors are equivalent, notably `|` in type annotations, which CPython 3.14 does not evaluate.

Accepted without a unit: pinning CI tool images by digest (SEC-6) goes to a Renovate follow-up; moving the `ZoneInfo` zone CHECK to a reference table (RT-1 fix item) is not needed once 16c lets the owner repair an invalid row.

## Coverage of the acceptance criteria

| AC | Unit |
| --- | --- |
| AC-1 | 01, 03, 08, 13, 14 |
| AC-2, AC-3 | 09, 07 |
| AC-3 (end to end) | 14 |
| AC-4 to AC-7 | 06a, 07 |
| AC-8, AC-9 | 01, 09, 10 |
| AC-10, AC-11 | 01, 09 |
| AC-12 | 03 |
| AC-13 | 05, 09 |
| AC-14 to AC-19 | 02, 10 |
| AC-20, AC-21 | 05, 11 |
| AC-22 to AC-26 | 03, 12 |
| AC-27 | 13 |
| AC-28 | 03 |
| AC-29 | 05, 09 |
| AC-30 | 04, 05, 15b |
| AC-31, AC-32 | 08 |
| AC-33 | 05, 07, 08, 09, 10 |
| AC-34 | 04 |
| AC-35, AC-36 | 05, 14 |

## Changes made during the build

- **U-quiet-hours-05b** (PR #31): `SettingsStore.read` wraps database errors in `SettingsStoreFailure`, found by the first challenge round.
- **U-quiet-hours-15a** (PR #34): delivered as `python -m app migrate` (a one-shot compose service and a Helm pre-install/PreSync Job) in the agent's own `compose.yaml` and `deploy/charts/worker`, not in a root `docker-compose.yml`. `serve` only checks that the schema is at the expected head (exit 5 when not, 6 when the migration failed). New setting: `MAIL_TRIAGE_RUNTIME_PASSWORD`.
- **U-quiet-hours-15b** (PR #37): the migrate service is **not** in the `prod-like` profile, because `docker compose up --wait` counts an exited container as failed, even with exit code 0 (found in CI). The `runtime-role` CI job starts the stack, runs `docker compose run --rm --build mail-triage-migrate`, then runs `tests/e2e/test_runtime_role.py`: 19 forbidden statements must fail with SQLSTATE 42501. The agent stays out of `prod-like` (it needs real Gmail, Telegram and Anthropic credentials). The Trivy scan of the `components` job covers the image with no ignores.
- **Secrets in the cluster** (PR #36): ADR-0029 chooses Sealed Secrets; the operator step is in `deploy/charts/worker/README.md`.

## Open points for the build

- Coverage at least 90 % on changed code; a mutation score of 85 % is a criterion of U-01 and U-03, and a CI step runs the mutation check.
- The plan of `web-settings` is made in its own phase 4.
