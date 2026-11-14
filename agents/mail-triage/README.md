# mail-triage

Reads Marco's incoming Gmail, files each mail under a category, warns him through Telegram when a mail needs immediate attention, and sends a confirmed reply. Spec: `docs/specs/mail-triage.md`; design: `docs/design/mail-triage-design.md`; plan: `docs/plans/mail-triage.md`.

Status: in use. Adjustable quiet hours (INT-002, spec `docs/specs/adjustable-quiet-hours.md`) are built; the web settings page is the separate, later feature `web-settings`.

## Configuration

All values come from the environment (`.env` locally, a Kubernetes secret in production). The agent refuses to start when one is missing or invalid, and the message names the key, never the value.

| Variable | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (secret) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (secret) |
| `TELEGRAM_ALLOWED_USER_ID`, `TELEGRAM_ALLOWED_CHAT_ID` | The only user and chat the bot answers (Marco) |
| `MODEL_SMALL`, `MODEL_LARGE` | Model ids; never literals in code |
| `DATABASE_URL` | PostgreSQL connection string of the **runtime role** `mail_triage_runtime` (contains the password) |
| `POLL_INTERVAL_SECONDS` | Optional; default 60 |
| `ENVIRONMENT` | Optional; `production` (default), `development` or `test`. Production refuses a `DATABASE_SSL` other than `verify-full` |
| `DATABASE_SSL` | Optional; `verify-full` (default), `verify-ca`, `require` or `disable`. Also read by the migrate command |
| `DATABASE_CA_FILE` | Optional; PEM file with the CA of the database certificate; empty uses the system trust store |

These are the names the process reads. In `.env` and `.env.example` the same values carry the prefix `MAIL_TRIAGE_` where compose maps them (see the table below).

### Two commands, two database roles (ADR-0025, ADR-0030)

The agent starts in two steps. The first runs once as the database owner, the second runs for as long as the agent lives.

1. `python -m app migrate` is the one-shot job (compose service `mail-triage-migrate`, Helm PreSync Job; see [the worker chart](../../deploy/charts/worker/README.md)). It connects as the owner role and, under a PostgreSQL advisory lock so that two jobs never migrate at the same time:
   - applies the Alembic migrations;
   - creates or updates the login role `mail_triage_runtime` with a SCRAM-SHA-256 verifier that the job computes itself, so the clear password never reaches the server or its log. The job also sets `NOREPLICATION NOBYPASSRLS` and fails if the role is a member of another role;
   - applies `app/db/grants.sql`;
   - runs the retention purge as its last step (below).

   It can be run again safely. It reads only `DATABASE_OWNER_URL`, `RUNTIME_ROLE_PASSWORD` and `WEB_ROLE_PASSWORD` (all secrets); a missing key stops it with exit code 2 naming the key, and any other failure exits with 6; a failing purge exits with 6 and the log names the `purge` step. TLS comes from `DATABASE_SSL` and `DATABASE_CA_FILE`, not from the URL (an `ssl` value inside it is ignored).
2. `python -m app` (= `serve`) runs the agent as the runtime role, which owns nothing and cannot run DDL. It does not migrate: at start it only checks that the schema is at the Alembic head of its image, and otherwise exits with code 5 ("run the migrate job"). The agent never receives the owner URL.

`python -m app.consent` (the one-time Gmail consent) no longer creates tables either. It stops and names the migrate job when the schema is not current, so run the migrate job first.

### Retention purge (U-web-settings-49)

The last step of the migrate job, run as the owner role, deletes `settings.settings_change` rows older than one year and
`web_auth.security_event` rows older than 90 days (a row goes when it is strictly older than the cutoff; one that is
exactly as old stays until the next run), plus expired `web_auth.login_request` and `web_auth.session` rows. It logs only
the number of removed rows per table and is safe to repeat. `python -m app purge` runs the step alone with the same
owner settings. It is the one delete path for `settings_change`: the runtime roles still cannot delete or truncate it.
There is no CronJob and no other workload holds the owner secret.

| Exit code | Meaning |
|---|---|
| 2 | Missing or invalid configuration (names the key, never the value) |
| 3 | No Gmail consent stored yet |
| 4 | Another copy of the agent holds the lock |
| 5 | `serve`: the schema is not at the expected head, run the migrate job |
| 6 | `migrate` or `purge`: the migration or the purge failed |

| Where | Variable | Meaning |
|---|---|---|
| `.env` (compose) | `MAIL_TRIAGE_DATABASE_URL` | Optional. Leave empty locally; compose then builds the runtime URL from `MAIL_TRIAGE_RUNTIME_PASSWORD`. In production, a full URL of the runtime role |
| `.env` (compose) | `MAIL_TRIAGE_RUNTIME_PASSWORD` | Password of `mail_triage_runtime`; the migrate job passes it to the job as `RUNTIME_ROLE_PASSWORD` |
| `.env` (compose) | `WEB_ROLE_PASSWORD` | Password of `web_settings_runtime`, the role of the web app; the migrate job creates the role with it |
| `.env` (compose) | `MAIL_TRIAGE_DATABASE_OWNER_URL` | Optional override of the owner URL; compose otherwise connects as the database's bootstrap user with `POSTGRES_PASSWORD` |
| migrate job | `DATABASE_OWNER_URL`, `RUNTIME_ROLE_PASSWORD`, `WEB_ROLE_PASSWORD` | What the job reads (secrets; in Kubernetes the migration Secret) |
| agent | `DATABASE_URL` | What the agent reads (runtime role) |

Locally, `docker compose --profile dev up` (or `--profile components`) starts `mail-triage-migrate` first; `mail-triage` starts when it has completed successfully. The migrate service is not in `prod-like`, because `up --wait` counts a container that has exited as failed.

### What the runtime role may do

`app/db/grants.sql` is the single list of rights, one grant per table by what the code does (ADR-0030):

- the mail audit trail (`audit_log`, `overview_log`) is append-only: select and insert, never update or delete;
- mail, alert, draft, token, poll and catch-up tables: select, insert and update, never delete;
- `conversation` (the one pending dialogue) and the web tables the agent keeps itself (`web_notice_token`, the one row of `web_auth.web_lock`): the only tables with delete (`grants.sql`);
- `web_auth.security_event`: column select of `id`, `kind`, `at` and `count`, nothing else (the wrong-code alert, ADR-0039);
- `settings.schedule`: select, insert and update of the single settings row. The change history `settings.settings_change` can only be read; only the owner purge deletes from it (below).

Two triggers on `settings.schedule` make the database, not the application, decide what a change is. The guard refuses a write that does not raise `version` by exactly one and a write whose channel does not match the login role. The audit trigger writes one record per change (time, channel, actor, old and new values, and the login role taken from `session_user`), so the runtime role means the channel `telegram` and cannot claim another one. The runtime role cannot insert into the history directly.

## Settings that Marco changes

Quiet hours, the daily overview time, the remind-me-later default and the time zone are stored in the database (schema `settings`, ADR-0025) and changed with `/settings` in Telegram; the user guide is [Quiet hours and other settings in Telegram](../../docs/user-guide/quiet-hours.md). Validation and the place list (ADR-0028) live in the shared package `packages/schedule-policy`, and the dialogue keeps its state in one `conversation` table (ADR-0026). Wall-clock rules for gaps and repeated hours are in ADR-0027. With no stored row the agent uses the first-release values. If the stored row cannot be read or is invalid, the agent uses the last good values (or the defaults) and sends Marco one Telegram notice per incident.

### Telegram update id

`poll_state.telegram_update_id` holds the id of the last Telegram update that was handled. The id is stored after the update has been handled, and it only moves forward. Telegram redelivers an update that was not acknowledged, for example after a restart; typed text is read as the answer to whatever question is open, so a redelivered answer could otherwise be taken as the answer to the next question. On start the agent skips every update at or below the stored id. If handling fails, the id is not stored and the update is handled again.

## Catch-up of old unread mail

New mail is handled as it arrives. The unread mail that was already in the inbox when the agent first ran is filed once, by itself (INT-003, ADR-0021; spec `docs/specs/mail-triage-backlog.md`):

- It starts at the first mail cycle that finds no catch-up state, also on an agent that has been running for some time. There is no command and no setting.
- It handles at most 20 mails per cycle, newest first, and always after the new mail of that cycle.
- It only uses the daily model budget above a reserve of 50 calls, so a mail that arrives later in the day can still be judged. When the budget is used up it waits for the next day; the remaining mails stay untouched in the inbox.
- At most 5 Telegram alerts come from it; other urgent old mail is listed once in the daily overview.
- Read mail, mail outside the inbox and the agent's own sent mail are not touched, and nothing is deleted or sent.
- `select started_at, finished_at from catchup_state` shows where it is. The daily budget counter is in memory, so after a restart the reserve holds again only from the next day.

## Develop

Test and check: `node scripts/components.mjs check mail-triage` (from the repository root).
