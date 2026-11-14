# deploy/local

Files of the local week-test stack (U-web-settings-73). Start with `docs/operations/local-stack.md`.

- `stack.env` is checked in and holds settings without secrets: the agent runs with `ENVIRONMENT=production` and
  `DATABASE_SSL=verify-full`. `scripts/local-stack.mjs` passes it to `docker compose` after your `.env`.
- `secrets.env` is made by `node scripts/local-stack.mjs init`. It is git-ignored and never printed. Do not commit or share it.
  It also holds `MAIL_TRIAGE_RUNTIME_PASSWORD` when your `.env` has none; `.env` is never edited. A
  `MAIL_TRIAGE_DATABASE_URL` line in `.env` overrides that password (remove an old owner-login URL; `up` warns).
- `node scripts/local-stack.mjs consent` is the one-time Gmail consent (also needed again after a new
  `MAIL_TRIAGE_TOKEN_ENCRYPTION_KEY`). It runs the one-shot service `mail-triage-consent` (profile `local` only), whose
  port is published on `127.0.0.1:8765` of this computer only. Register `http://127.0.0.1:8765/callback` as a redirect
  address of the Google client. See `docs/operations/local-stack.md`.
- `backups/` holds the database dumps that `up` and `backup` write. Git-ignored; the dumps contain your data.
