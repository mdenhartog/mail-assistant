# Architecture

The overview diagram of the mail-triage agent is [mail-triage-architecture.html](mail-triage-architecture.html)
(source: `mail-triage-architecture.json`). It shows the ports and adapters of the agent. This page adds the parts that
the adjustable quiet hours (INT-002) introduced. The diagram does not show them yet.

## Components of mail-triage

| Part | Where | Responsibility |
|---|---|---|
| Core | `agents/mail-triage/app/core` | Pure logic without I/O: urgency, alert states, the text of alerts and of the settings dialogue |
| Use cases | `agents/mail-triage/app/usecases` | Triage, alert delivery, overview, snooze, reply, the settings dialogue and its confirmation |
| Adapters | `agents/mail-triage/app/adapters`, `app/db` | One adapter per outside system: Gmail, Anthropic, Telegram, PostgreSQL |
| `schedule_policy` | `packages/schedule-policy` | Shared Python package: the `TimePolicy` model, the validation of a whole row, the typed-time parser and the place list. The agent uses it now; the later web backend uses the same code (ADR-0025, ADR-0028) |
| Migrate job | `python -m app migrate` | One-shot job run before the agent: migrations, runtime role and grants (ADR-0025, ADR-0030) |

## Data and where it lives

PostgreSQL holds everything. The agent's Alembic chain is the only migrator.

| Data | Place | Note |
|---|---|---|
| Mail, alerts, drafts, the Gmail token, audit and overview log | schema `public` | Append-only audit tables; see the grants in `app/db/grants.sql` |
| The four settings | `settings.schedule` (one row with a `version`) | Every write replaces the whole row with a version check (ADR-0023, ADR-0025) |
| History of settings changes | `settings.settings_change` | Written by a database trigger only: time, channel, actor, old and new values |
| The pending Telegram dialogue | `conversation` (one row) | Snooze, reply and settings questions share it (ADR-0026) |
| Update cursor | `poll_state.telegram_update_id` | The last handled Telegram update, so a restart does not replay it |

## Start-up and trust boundaries

1. The migrate job connects as the database owner role, takes an advisory lock, migrates, sets up the login role
   `mail_triage_runtime` and applies its grants. Only this job holds the owner credentials.
2. The agent connects as `mail_triage_runtime`. It owns nothing, cannot run DDL, and at start only checks that the
   schema is at the expected head (exit 5 when not).
3. The database derives the channel and the actor of a settings change from the login role, so the agent cannot
   claim another channel (ADR-0030).
4. In Kubernetes the migrate job is a PreSync hook of the `worker` chart, and the secrets are sealed
   (ADR-0029); see [the worker chart](../../deploy/charts/worker/README.md).

## Decisions

| ADR | Subject |
|---|---|
| [ADR-0023](../memory/decisions/ADR-0023-settings-shared-table.md) | Settings in a shared PostgreSQL table |
| [ADR-0025](../memory/decisions/ADR-0025-settings-contract.md) | Settings contract, schema, roles and shared package |
| [ADR-0026](../memory/decisions/ADR-0026-single-conversation-state.md) | One conversation state for all Telegram dialogues |
| [ADR-0027](../memory/decisions/ADR-0027-wall-clock-resolution.md) | Wall-clock rules for gaps and repeated hours |
| [ADR-0028](../memory/decisions/ADR-0028-place-list.md) | The place list for time-zone lookup |
| [ADR-0029](../memory/decisions/ADR-0029-secrets-sealed-secrets.md) | Cluster secrets with Sealed Secrets |
| [ADR-0030](../memory/decisions/ADR-0030-runtime-role-hardening.md) | Runtime role hardening |
