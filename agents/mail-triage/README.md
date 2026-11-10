# mail-triage

Reads Marco's incoming Gmail, files each mail under a category, warns him through Telegram when a mail needs immediate attention, and sends a confirmed reply. Spec: `docs/specs/mail-triage.md`; design: `docs/design/mail-triage-design.md`; plan: `docs/plans/mail-triage.md`.

Status: skeleton and configuration (unit U-01). The polling loop and the adapters arrive in later units.

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

### Two commands, two database roles (ADR-0025)

- `python -m app` (= `serve`) runs the agent as the runtime role, which owns nothing. It does not migrate: at start it checks that the schema is at the Alembic head of its image and otherwise exits with code 5 ("run the migrate job").
- `python -m app migrate` is the one-shot job (compose service `mail-triage-migrate`, Helm PreSync Job). It reads only `DATABASE_OWNER_URL` (owner role, secret) and `RUNTIME_ROLE_PASSWORD` (secret), migrates under an advisory lock, creates or updates the role `mail_triage_runtime` and applies `app/db/grants.sql`. A missing key stops it with exit code 2 naming the key; any other failure exits with 6. It can be run again safely. The agent never receives the owner URL.
- Locally the owner is the database's bootstrap user (`POSTGRES_PASSWORD`); set `MAIL_TRIAGE_RUNTIME_PASSWORD` in `.env` for the runtime role.

Quiet hours, the daily overview time, the snooze default and the time zone are constants in code (spec C7); making them adjustable is INT-002.

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
