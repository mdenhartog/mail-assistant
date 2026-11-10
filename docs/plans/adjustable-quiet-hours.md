---
intent: INT-002
feature: adjustable-quiet-hours
spec: docs/specs/adjustable-quiet-hours.md
design: docs/design/adjustable-quiet-hours-design.md
threat-model: docs/security/adjustable-quiet-hours-threat-model.md
status: approved
date: 2026-11-09
---

# Plan: adjustable-quiet-hours

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

## Units

### U-quiet-hours-01: Schedule policy, validation and time parsing

- Layer: backend (shared package)
- Contract: `TimePolicy` (frozen: zone, quiet_start, quiet_end, overview_at, remind_at), `DEFAULT_POLICY`, `validate(policy) -> list[Problem]` (rule id, value given, example), `parse_time(text) -> time | None` (C-3); test helpers `make_policy`, `FakeClock`.
- Files: `packages/schedule-policy/pyproject.toml`, `schedule_policy/policy.py`, `schedule_policy/parse.py`, `schedule_policy/testing.py`, `packages/schedule-policy/tests/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-pydantic
- Criteria:
  1. Given the defaults, When validated, Then there are no problems (AC-1) (type: happy).
  2. Given windows 23:00-07:00, 07:00-19:00, 07:00-08:00, When validated, Then valid; Given 07:00-19:01, 07:00-07:30, 23:00-23:00, Then each refused with its rule and an example (AC-10) (type: edge).
  3. Given overview 06:00 with window 23:00-07:00, or overview 18:00 with window 17:00-03:00, When validated, Then refused naming the overview, with a suggested move outside the window (AC-11) (type: error).
  4. Given the times `7`, `7:00`, `07:00`, `0700`, `19.30`, `7am`, `7:30pm`, `24:00`, When parsed, Then each gives the right clock time (AC-8) (type: happy).
  5. Given `abc`, `25:00`, `07:00:30`, a full-width `０７:００`, empty text, 65 characters, a control character, an emoji, When parsed, Then `None` (AC-9) (type: security).
  6. Given an unknown zone name or a path-like name, When validated, Then refused (type: security).
  7. Given any policy that passes validation, When the window length is computed on any day, Then it is 1 to 12 hours in clock minutes (property test) (type: edge).
  8. Given a reminder default inside the window, or an overview or reminder time exactly at the window start (refused) or at its end (valid), When validated, Then the start-inclusive, end-exclusive rule applies (type: edge).
  9. Given the property test, When run, Then it uses a fixed seed (`derandomize`) and the 59/60 and 720/721-minute boundaries are explicit rows (type: edge).
  10. Given mutation testing on `policy.py` and `parse.py`, When run, Then the score is at least 85 % (boundary mutants `<` vs `<=`, 59 vs 60, 720 vs 721 are killed) (type: security).

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

### U-quiet-hours-02: Place list and lookup

- Layer: backend (shared package)
- Contract: `places.lookup(text) -> LookupResult` (hits with label and UTC offset, near-miss suggestion, or nothing); countries with several zones return city-named zones; a typed IANA name is accepted if listed (ADR-0028).
- Files: `schedule_policy/places.py`, `schedule_policy/places.json`, `packages/schedule-policy/tests/test_places.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python
- Criteria:
  1. Given "New York" in any case or accent, When looked up, Then America/New_York (AC-14) (type: happy).
  2. Given "Paris", "Sydney", "Georgia", When looked up, Then at most 5 labelled hits (AC-15) (type: edge).
  3. Given "Nwe York", When looked up, Then the suggestion "New York" (AC-16) (type: error).
  4. Given text matching nothing, When looked up, Then an empty result (AC-17) (type: error).
  5. Given "USA" and "Australia", When looked up, Then zones with city names (AC-18) (type: happy).
  6. Given "Europe/Paris", When looked up, Then accepted; Given an unlisted IANA name, Then nothing (AC-19) (type: edge).
  7. Given aliases "NYC", "Wien", "Den Haag", surrounding spaces and "Zürich", When looked up, Then matched (type: edge).
  8. Given the list, When checked against `tzdata`, Then every zone exists and every entry has a label (type: security).
  9. Given a 64-character and a 65-character text, When looked up, Then the second is refused before matching (AC-9) (type: security).
  10. Given NFC and NFD "Zürich", a Turkish dotless i, full-width Latin letters and "São Paulo", When looked up, Then each matches (type: edge).
  11. Given "Georgia", When looked up, Then both the country and the US state hits are offered (type: edge).

### U-quiet-hours-03: Rebuild time_policy on TimePolicy (core and callers, one PR)

- Layer: backend
- Contract: `in_quiet_hours`, `next_quiet_end`, `next_overview`, `remind_due` (the old `snooze_due` is renamed `remind_due(now, amount, policy)`) and `day_start` take a `TimePolicy` and compare UTC moments (ADR-0027). The module constants are removed. Two units on one branch: 03a the core functions and their tests; 03b the callers (`overview.py`, `deliver_alerts.py`, `snooze.py`, `triage.py`) pass `DEFAULT_POLICY` until U-12 and U-13 replace it.
- Files: 03a `app/core/time_policy.py`, `tests/core/test_time_policy.py`; 03b `app/usecases/overview.py`, `deliver_alerts.py`, `snooze.py`, `triage.py`, `tests/usecases/test_overview.py` (the `OVERVIEW_AT` monkeypatch becomes `replace(DEFAULT_POLICY, overview_at=...)`), `tests/usecases/test_snooze.py`
- Depends on: U-quiet-hours-01b
- Parallel: no
- Guardrails: guardrail-python
- Criteria:
  1. Given the existing time_policy tests with `DEFAULT_POLICY`, When run, Then they pass unchanged (AC-1) (type: happy).
  2. Given quiet hours 01:00-06:00, When asked at 23:30, 03:00, 06:00, Then not quiet, quiet, not quiet (AC-12) (type: edge).
  3. Given zone America/New_York with 23:00-07:00, When the moment is 23:30 New York time, Then quiet (AC-23) (type: happy).
  4. Given Europe/Amsterdam, America/New_York and one midnight-change zone on both clock-change days, When quiet hours, next quiet end, next overview and the remind due moment run for a time in the gap and a time that occurs twice, Then results follow ADR-0027 (AC-28) (type: edge).
  5. Given a 12 h window on a 23 h and a 25 h day, When validated and asked, Then both agree (AC-28) (type: edge).
  6. Given `now` exactly at the quiet start and the quiet end, When asked, Then quiet from the start, not quiet at the end (type: edge).
  7. Given a `now` without a time zone, When asked, Then an error (type: error).
  8. Given a `now` in a non-UTC zone, and one function called with two policies of different zones, When asked, Then results are correct (no `ZoneInfo` cache effect) (type: edge).
  9. Given Asia/Kolkata (UTC+5:30), Asia/Kathmandu (UTC+5:45) and Australia/Sydney (southern flip), When asked, Then results are correct (type: edge).
  10. Given a search of `app/` for `TIME_ZONE|QUIET_START|QUIET_END|OVERVIEW_AT|TOMORROW_AT`, When run, Then there is no hit outside the policy code (type: happy).
  11. Given mutation testing on `time_policy.py`, When run, Then the score is at least 85 % (type: security).

### U-quiet-hours-04: Migration 0004: settings schema, trigger, constraints

- Layer: backend (database)
- Contract: schema `settings` with `schedule` (single row, version, CHECKs) and `settings_change` (append-only, filled by a trigger); table `conversation` (single row); column `alert.release_at`. Run under the owner role; the runtime role gets minimal grants from one SQL source (ADR-0025, ADR-0026). Upgrades and downgrades cleanly.
- Files: `migrations/versions/0004_settings.py`, `app/db/models.py`, `app/db/grants.sql` (the one source of the role grants, also used by U-15a), `tests/db/test_settings_migration.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given revision 0003 with alerts, When migrated, Then the tables exist, alerts keep their data and `release_at` is null (type: happy).
  2. Given the migration, When downgraded, Then the schema, tables and column are gone and other data is unchanged (type: edge).
  3. Given a parametrised table with one row per CHECK name (minutes out of range, start equal to end, window outside 60-720 minutes, overview or remind inside the window, bad zone pattern, second row), When inserted directly, Then PostgreSQL refuses each (AC-34) (type: security).
  4. Given a row insert or update, When it succeeds, Then `settings_change` has a record with via, by, old and new, written by the trigger (AC-30) (type: happy).
  5. Given a runtime role created in the test from `grants.sql`, When it updates, deletes or truncates `settings_change`, runs DDL, or changes `session_replication_role`, Then PostgreSQL refuses (SQLSTATE 42501) (AC-30) (type: security).
  6. Given a fresh database, When all migrations run, Then the models match the schema (no drift) (type: happy).
  7. Given `settings_change`, When its columns are inspected, Then via and by are length-limited and there is no free-text column (type: security).

### U-quiet-hours-05: Settings store

- Layer: integration (testcontainers PostgreSQL, `tests/db/conftest.py`) and contract
- Contract: `SettingsStore.read() -> StoredSettings | None` (policy, version, updated info); `write(policy, expected_version, via, by) -> StoredSettings` (whole row, validated, version check, `VersionConflict`); `undo(expected_version)`. Row-to-policy uses the shared validation.
- Files: `app/db/pg_settings_store.py`, `app/db/repos.py`, `tests/db/test_settings_store.py`, `packages/schedule-policy/contract/settings_cases.json` (shared with `web-settings`)
- Depends on: U-quiet-hours-01, U-quiet-hours-04
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given no row, When read, Then `None`; When written with version 0, Then version 1 (type: happy).
  2. Given two sessions that read the same version and an explicit barrier (no sleeps), When both write, Then exactly one succeeds, the other gets `VersionConflict`, exactly one audit record exists and the row passes validation (AC-29) (type: edge).
  3. Given an invalid policy, When written, Then refused before the database and nothing changes (type: error).
  4. Given a write, When it commits, Then exactly one audit record exists (AC-30) (type: happy).
  5. Given an undo with the current version, Then the previous values return; with an old version, Then `VersionConflict` (AC-21) (type: edge).
  6. Given the shared fixture file of valid and invalid cases, When run through the store, Then the outcomes match the package (AC-36) (type: happy).
  7. Given a failure between validation and commit, When it happens, Then nothing is stored (AC-13) (type: error).
  8. Given a write to `Pacific/Kiritimati` and a failure path, When logs are captured, Then no record contains the zone or a token (AC-33) (type: security).

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

### U-quiet-hours-07: Router registry, tokens and expiry

- Layer: backend
- Contract: `CommandRouter` dispatches to registered handlers (settings, snooze, reply); slash commands before awaited text; settings buttons `set:<key>:<nonce>`, `tz:<index>:<nonce>`, `cancel:<nonce>`, `undo:<nonce>`; replayed `update_id` ignored; expired questions edit their message.
- Files: `app/usecases/dispatch.py`, `app/adapters/telegram_inbox.py`, `app/adapters/telegram_outbox.py`, `tests/usecases/test_dispatch.py`, `tests/adapters/test_telegram_inbox.py`
- Depends on: U-quiet-hours-06a
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given a fake registered handler and a pending snooze question, When `/settings` and a change start, Then the old question is replaced, the bot says what was dropped, and later text is read only as the settings answer (AC-5) (type: edge).
  2. Given a button with an old nonce, or forwarded to another chat, When tapped, Then nothing changes and a fresh card is offered (AC-4) (type: security).
  3. Given a user or chat that is not allowed, When any command or button arrives, Then nothing is answered (AC-3) (type: security).
  4. Given a replayed Telegram update, When it arrives twice, Then it is handled once (type: security).
  5. Given Cancel, When tapped, Then the old value stays and no row is written (AC-7) (type: happy).
  6. Given a button tap, When handled, Then the callback is answered so no spinner remains (type: happy).
  7. Given an injected `FakeClock`, When the expiry table 14:59:59, 15:00:00, 15:00:01 runs, Then used, expired, expired; the old message is edited to "Expired" without buttons and "Start again" is offered (AC-6) (type: edge).
  8. Given text that arrives with no pending question after expiry, When handled, Then the usual "use the buttons" answer is given, never a settings answer (type: error).
  9. Given a pending settings question, When an old snooze button is tapped, Then the settings question stays intact (type: edge).
  10. Given a double tap, or a callback and a text at once, When handled, Then only one write happens (type: edge).
  11. Given a tap from another chat id with a valid nonce, When handled, Then it is ignored; the allowed-user and chat check stays in the Telegram intake and has its own test (AC-3, AC-4) (type: security).
  12. Given a failure path, When logs are captured, Then no token or zone value appears (AC-33) (type: security).

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

### U-quiet-hours-08: PolicySource with fallback and notice

- Layer: integration (testcontainers PostgreSQL) with a fake slow port and `FakeClock`
- Contract: `PolicySource.current() -> TimePolicy`: reads with a 2 s timeout, validates, keeps a last-good policy in memory, returns `DEFAULT_POLICY` if none; logs `settings_invalid` or the error class without values; asks the notifier for one notice per incident.
- Files: `app/db/pg_policy_source.py`, `app/usecases/policy_notice.py`, `tests/db/test_policy_source.py`
- Depends on: U-quiet-hours-01, U-quiet-hours-05
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a stored valid row, When read, Then its policy; Given no row or no table, Then `DEFAULT_POLICY` (AC-1) (type: happy).
  2. Given an invalid row (unknown zone, 13 h window, overview inside the window, NULL), When read, Then last good or default, `settings_invalid` logged with the key only, and one notice (AC-31) (type: error).
  3. Given connection refused, timeout, permission error and a missing table (real database before migration), and a fake read slower than 2 s (injected clock, no `pg_sleep`), When read, Then the fallback within the timeout, the error class logged, one notice per incident (AC-32) (type: error).
  4. Given a good read, then a corrupted row, then a read, When run, Then the first values are used; Given a fresh process, Then the defaults (type: edge).
  5. Given any change or error, When logged, Then `Pacific/Kiritimati` never appears in any captured record and no token appears (AC-33) (type: security).
  6. Given an incident that continues over several reads, When it persists, Then only one notice is sent until it recovers (type: edge).

### U-quiet-hours-09: Settings dialogue: card, times, quiet hours, conflicts

- Layer: backend
- Contract: `SettingsDialog` handles `/settings`, the card, the time questions for the overview and the reminder default, the two-step quiet hours, refusal texts with rule and example, and the one-tap move of a conflicting value.
- Files: `app/usecases/settings_dialog.py`, `app/core/settings_text.py`, `tests/usecases/test_settings_dialog.py`
- Depends on: U-quiet-hours-01, U-quiet-hours-05, U-quiet-hours-07
- Parallel: yes (with U-06b)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given the allowed user, When `/settings` is sent, Then four labelled values with a "Change" button each (AC-2) (type: happy).
  2. Given the quiet-hours question, When a valid start and end come, Then both are stored together (AC-13) (type: happy).
  3. Given a valid start and then Cancel, an invalid end, or a database fault between the steps, When it happens, Then neither value is stored (AC-13) (type: error).
  4. Given the 22:00-11:00 answer, When refused, Then the message names the rule, the value and "Try 22:00 to 10:00" (type: error).
  5. Given overview 18:00 and a new window 17:00-03:00, When saved, Then refused and a one-tap move of the overview is offered; taking it stores both (AC-11) (type: edge).
  6. Given the time forms and refused texts of U-01, When answered in the dialogue, Then stored or refused as there, and nothing reaches a query (AC-8, AC-9) (type: security).
  7. Given a `VersionConflict`, When saving, Then the bot says it changed elsewhere and shows the card again (AC-29) (type: edge).
  8. Given each question, Then it names the value and the step and has a Cancel button (type: a11y).
  9. Given a failure path, When logs are captured, Then no token or zone value appears (AC-33) (type: security).

### U-quiet-hours-10: Zone dialogue

- Layer: backend
- Contract: the time-zone question in `SettingsDialog`: lookup per U-02, buttons for several hits and for large countries, the near-miss suggestion, the nothing-found message with a hint and Cancel, storing the chosen zone.
- Files: `app/usecases/settings_dialog.py`, `app/core/settings_text.py`, `tests/usecases/test_zone_dialog.py`
- Depends on: U-quiet-hours-02, U-quiet-hours-09
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given "New York", When answered, Then America/New_York is stored (AC-14) (type: happy).
  2. Given "Paris", When answered, Then at most 5 buttons "Paris, France (UTC+1)"; the chosen one is stored (AC-15) (type: edge).
  3. Given "Nwe York", When answered, Then "Did you mean New York?" with buttons (AC-16) (type: error).
  4. Given nothing found, When answered, Then the bot says so, suggests the nearest big city or the country, shows Cancel, stores nothing (AC-17) (type: error).
  5. Given "USA", When answered, Then zone buttons with city names (AC-18) (type: happy).
  6. Given `../etc` or SQL text, When answered, Then nothing is stored and the zone lookup is not called with it (AC-9) (type: security).
  7. Given a button for an index outside the stored candidates, When tapped, Then nothing changes (type: security).
  8. Given `Europe/Paris` typed, Then stored; Given an unlisted IANA name such as `Pacific/Kiritimati`, Then nothing found and the name never appears in logs (AC-19, AC-33) (type: security).

### U-quiet-hours-11: Confirmation and Undo

- Layer: backend
- Contract: after a successful write the bot sends the full picture (zone with UTC offset, local time there and in the previous zone, quiet hours in both, next overview, next clock change within 14 days) and an Undo button; Undo calls `SettingsStore.undo`.
- Files: `app/usecases/settings_confirm.py`, `app/core/settings_text.py`, `tests/usecases/test_settings_confirm.py`
- Depends on: U-quiet-hours-10
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given a zone change to America/New_York at a fixed UTC moment (`FakeClock`), When confirmed, Then the text has the offset, 17:05 there and 23:05 Amsterdam, the quiet hours in both, the next overview (AC-20) (type: happy).
  2. Given a clock change within 14 days, When confirmed, Then the date is mentioned; Given none, Then not (type: edge).
  3. Given Undo with an unchanged row, When tapped, Then the previous values return and a new confirmation is sent (AC-21) (type: happy).
  4. Given Undo after another change, When tapped, Then nothing changes and the bot says so (AC-21) (type: edge).
  5. Given a confirmation of a non-zone change, Then the quiet hours and times are shown without a zone comparison (type: edge).
  6. Given Asia/Kolkata, When confirmed, Then the offset is labelled "UTC+5:30" (type: edge).
  7. Given Undo tapped after 15 minutes or after a restart, When handled, Then it works if the row is unchanged, otherwise the bot says so (AC-21) (type: edge).

### U-quiet-hours-12: Policy snapshot in delivery, snooze and triage

- Layer: backend
- Contract: `AlertDelivery`, `SnoozeService` and `Triage` take a `TimePolicy` snapshot per operation from `PolicySource`; a held alert gets `release_at` (next quiet end under the snapshot) and is released when `now >= release_at`; a snooze that becomes due inside quiet hours is held and released at the quiet end valid then.
- Files: `app/usecases/deliver_alerts.py`, `app/usecases/snooze.py`, `app/usecases/triage.py`, `app/db/pg_store.py`, `tests/usecases/test_deliver_alerts.py`
- Depends on: U-quiet-hours-03, U-quiet-hours-04, U-quiet-hours-06a, U-quiet-hours-08
- Parallel: yes (with U-13)
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a stored change, When the next alert arises, Then it is judged with the new values (AC-22) (type: happy).
  2. Given zone America/New_York and quiet hours 23:00-07:00, When an urgent mail arrives at 23:30 New York time, Then its alert is held (AC-23) (type: happy).
  3. Given a snoozed alert, When a change is stored, Then its due moment does not move (AC-24) (type: edge).
  4. Given an alert held at 02:00 with release 07:00, When quiet hours become 23:00-05:00 at 03:00, Then it is still released at 07:00; an alert held after the change uses the new hours (AC-25) (type: edge).
  5. Given a snooze due inside the new quiet hours, When it falls due, Then it is held and released at that quiet end (AC-26) (type: edge).
  6. Given a `PolicySource` fake that returns a different policy on its second call, When one operation runs, Then the whole operation used the first snapshot (type: edge).

### U-quiet-hours-13: Overview window across zone changes

- Layer: backend
- Contract: the daily overview takes its window from the last settled instant, uses the policy zone for the "already sent for this date" check, and has no `TIME_ZONE`/`OVERVIEW_AT` constants; the dead "yesterday" branch is removed.
- Files: `app/usecases/overview.py`, `tests/usecases/test_overview.py`
- Depends on: U-quiet-hours-03, U-quiet-hours-08
- Parallel: yes (with U-12)
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the overview sent today in Europe/Amsterdam, When the zone becomes America/New_York the same evening, Then no second overview for that local date, no filed mail is dropped, and the next is at 18:00 New York time (AC-27) (type: edge).
  2. Given the existing overview tests with `DEFAULT_POLICY`, When run, Then they pass unchanged (AC-1) (type: happy).
  3. Given a zone change from New York back to Amsterdam, When the day is repeated or skipped locally, Then every filed mail appears in exactly one overview (AC-27) (type: edge).
  4. Given a changed overview time, When the policy is read, Then the new time is used for the next overview only (type: happy).

### U-quiet-hours-14: Wiring and end-to-end

- Layer: backend
- Contract: wiring of `PolicySource`, the stores, the conversation store and the router in `wiring.py`/`runner.py`; end-to-end tests with a real PostgreSQL and a fake Telegram port; golden-master run of the first-release suites.
- Files: `app/wiring.py`, `app/runner.py`, `app/settings.py`, `tests/db/test_settings_end_to_end.py`
- Depends on: U-quiet-hours-06b, U-quiet-hours-11, U-quiet-hours-12, U-quiet-hours-13
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the settings schema absent, and separately an empty table, When the full existing suites run, Then they pass unchanged (AC-1) (type: happy).
  2. Given a Telegram change of the time zone, When the next run happens, Then quiet hours, overview and the remind default use the new values (AC-22) (type: happy).
  3. Given the agent compose profile started without the backend service, When a Telegram change is made, Then it is applied in the next run (AC-35) (type: edge).
  4. Given the agent and the shared package, When the contract fixture runs, Then both agree on the schema (AC-36) (type: happy).
  5. Given a stranger's `/settings` and a stranger's old button, When sent end to end, Then no row is written and nothing is sent (AC-3) (type: security).

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
