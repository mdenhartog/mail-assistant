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
| `DATABASE_URL` | PostgreSQL connection string (contains the password) |
| `POLL_INTERVAL_SECONDS` | Optional; default 60 |

Quiet hours, the daily overview time, the snooze default and the time zone are constants in code (spec C7); making them adjustable is INT-002.

## Develop

Test and check: `node scripts/components.mjs check mail-triage` (from the repository root).
