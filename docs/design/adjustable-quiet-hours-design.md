---
feature: adjustable-quiet-hours
intent: INT-002
spec: docs/specs/adjustable-quiet-hours.md
status: approved
date: 2026-11-09
approver: Marco
adrs: [ADR-0019, ADR-0023, ADR-0025, ADR-0026, ADR-0027, ADR-0028]
---

# Design: adjustable quiet hours (Telegram)

Prototype: not needed. Telegram has no screens of our own; the web page has its own design phase in `web-settings` (ADR-0009).

## Approach in one paragraph

The four constants of `time_policy.py` become one frozen value, `TimePolicy`, read from a single settings row at the start of each operation. A new shared package holds the pure parts (the policy, the validation, the time parsing and the place list) so the web backend can reuse them. A guided Telegram dialogue, built on one stored conversation state, changes the row with a version check. Everything that was a module constant in the agent now receives a policy snapshot (rebuild-not-patch: the old functions and the dead "yesterday" branch go).

## Components

```text
packages/schedule-policy (pure Python, no I/O)
  TimePolicy            zone, quiet_start, quiet_end, overview_at, remind_at  (frozen)
  DEFAULT_POLICY        the first-release values
  validate(policy)      whole-row rules of C-2, returns problems with a rule id and an example
  parse_time(text)      forms of C-3
  places.lookup(text)   ADR-0028: hits, near misses, zones per country

agents/mail-triage/app
  core/time_policy.py   rebuilt: functions of TimePolicy (in_quiet_hours, next_quiet_end,
                        next_overview, remind_due, day_start); UTC moments, ADR-0027
  ports:   PolicySource.current() -> TimePolicy      SettingsStore (read row, write with version, undo)
           ConversationStore (one row)                Notifier (existing outbox)
  usecases/settings_dialog.py   the guided dialogue (step table below)
  usecases/dispatch.py          CommandRouter -> thin registry: settings, snooze, reply
  usecases/deliver_alerts.py, snooze.py, overview.py, triage.py   take a TimePolicy snapshot
  db/pg_policy_source.py        reads settings.schedule, validates, last-good cache, 2 s timeout
  db/pg_settings_store.py       whole-row write with version check
  db/migrations 0004            schema + tables + trigger + CHECKs + conversation + alert columns
```

```text
Telegram ─► telegram_inbox ─► CommandRouter ─► SettingsDialog ─► SettingsStore ─► settings.schedule ──trigger──► settings.settings_change
                                    │                │
                                    │                └─ ConversationStore (nonce, step, partial values, expiry)
                                    └─ SnoozeService / ReplyService (same ConversationStore)
Runner cycle ─► PolicySource.current() ─► TimePolicy snapshot ─► AlertDelivery / Overview / Snooze / Triage
```

A diagram in the archify HTML format is produced when the plan is made (phase 4), together with the web part.

## Data model (migration 0004, run under the owner role)

- Schema `settings`.
- `settings.schedule`: `id smallint primary key check (id = 1)`, `zone text`, `quiet_start smallint`, `quiet_end smallint`, `overview_at smallint`, `remind_at smallint` (minutes after midnight), `version integer`, `updated_at timestamptz`, `updated_via text` (`telegram` or `web`), `updated_by text`. CHECKs: minutes 0 to 1439; `quiet_start <> quiet_end`; window length 60 to 720 minutes; overview and remind outside the window; zone matches `^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$`. No row means the defaults.
- `settings.settings_change`: append-only; `at`, `via`, `by`, `old` (jsonb), `new` (jsonb), filled by an `AFTER INSERT OR UPDATE` trigger on `settings.schedule`; the runtime role has `INSERT` through the trigger only and no `UPDATE`, `DELETE` or `TRUNCATE`.
- `conversation` (one row, `check (id = 1)`): `kind` (`snooze`, `reply`, `settings`), `target`, `step`, `partial` (jsonb), `nonce`, `expires_at`. It replaces `alert.awaiting_input` (dropped in the same migration).
- `alert.release_at timestamptz`: set when an alert is held (the next quiet end under the policy valid then); delivery releases a held alert when `now >= release_at` (C-4).
- Roles: an owner role runs migrations (the agent starts a migration job with owner credentials and runs with its runtime role); the runtime role owns nothing.

## Dialogue steps

| Step | Bot shows | Accepts | Next |
| --- | --- | --- | --- |
| card | four values, "Change" per value | button `set:<key>:<nonce>` | ask for the chosen value |
| time | "Daily overview: type a time, for example 18:00" + Cancel | text per C-3 | validate whole row, store, confirm |
| quiet 1 | "Quiet hours, step 1 of 2: start time" + Cancel | text | quiet 2 (start kept in `partial`) |
| quiet 2 | "step 2 of 2: end time" + Cancel | text | validate whole row, store both, confirm |
| zone | "Time zone: type a city or a country" + Cancel | text | lookup: 1 hit stores; several or near miss show buttons `tz:<index>:<nonce>` |
| conflict | "The overview at 18:00 would fall inside quiet hours. Move it to 12:00?" | button | store both together |
| confirm | the full picture (C-7) and Undo | button `undo:<nonce>` | restores the previous version if unchanged |

Slash commands are handled before awaited text. Starting a dialogue replaces the stored conversation and says what was dropped. Text that arrives with no active conversation gets the normal "not understood" answer.

## Reading the policy

`PolicySource.current()` returns a validated `TimePolicy`. It reads the row with a 2 s timeout. An invalid row, a missing table or a database error returns the last good policy (kept in memory, per process), or `DEFAULT_POLICY`, logs `settings_invalid` or the error class without values, and asks the notifier for one notice per incident. Each operation takes one snapshot; a held alert gets `release_at` from the snapshot; a snoozed alert keeps its UTC due moment.

## Overview and zone change

The daily overview window runs from the last settled instant, not from local midnight, so a zone change cannot skip or repeat mail (AC-27). `overview_log` stays keyed by local date and the "already sent for this date" check uses the date in the policy's zone at the time of sending.

## Code that changes

| File | Change |
| --- | --- |
| `app/core/time_policy.py` | rebuilt as functions of `TimePolicy` (from `packages/schedule-policy`); constants removed |
| `app/usecases/overview.py` | no `time_policy.TIME_ZONE` or `OVERVIEW_AT`; dead "yesterday" branch removed; window from last settled instant |
| `app/usecases/snooze.py`, `deliver_alerts.py`, `triage.py` | take a policy snapshot; held alerts get `release_at` |
| `app/usecases/dispatch.py` | `CommandRouter` becomes a registry; `awaiting` moves to `ConversationStore` |
| `app/settings.py` | gains `database_owner_url` for the migration job (secret) |
| `app/db/models.py`, migrations | as in the data model |
| deployment (`deploy/`, compose) | migration job with owner credentials; build context includes `packages/schedule-policy` |

## Packaging

`packages/schedule-policy` is a path dependency of `agents/mail-triage` now and of `backend` in `web-settings`; both Docker builds copy it. It depends only on `tzdata` and the standard library. The cooldown of ADR-0022 applies.

## Risks and how the design answers them

| Risk | Answer |
| --- | --- |
| A bad row silences alerts | validated on read, CHECKs in the database, notice to Marco (AC-31, AC-34) |
| Two writers | one row, version check, whole-row validation (AC-29) |
| Clock-change days | UTC moments and the ADR-0027 rule (AC-28) |
| Dialogue collisions | one conversation row, nonce buttons (AC-4, AC-5) |
| Held alerts moved by a change | `release_at` fixed at hold time (AC-25) |
| Migration surprise on a running agent | migration 0004 keeps the first-release behaviour when the settings row is absent (AC-1); the drop of `awaiting_input` happens after the data move |

## Units (outline; the plan is phase 4)

1. `packages/schedule-policy`: `TimePolicy`, validation, time parsing (with the C-3 and C-2 test tables).
2. Place list and lookup (ADR-0028) with its guard test.
3. Rebuild `time_policy` on `TimePolicy` with the DST table tests (AC-28); constants removed from callers.
4. Migration 0004, settings store, trigger, CHECKs, roles (AC-30, AC-34).
5. `PolicySource` with fallback and notice (AC-31, AC-32, AC-33).
6. Conversation state and the router registry (ADR-0026; AC-4 to AC-7).
7. Settings dialogue: card, times, quiet hours, conflicts (AC-2, AC-8 to AC-13).
8. Zone dialogue (AC-14 to AC-19).
9. Confirmation and Undo (AC-20, AC-21).
10. Held and snoozed alerts, overview window (AC-22 to AC-27).
11. End-to-end: agent without backend, golden-master regression (AC-1, AC-35, AC-36).
