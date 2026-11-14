# deploy/local

Files of the local week-test stack (U-web-settings-73). Start with `docs/operations/local-stack.md`.

- `stack.env` is checked in and holds settings without secrets: the agent runs with `ENVIRONMENT=production` and
  `DATABASE_SSL=verify-full`. `scripts/local-stack.mjs` passes it to `docker compose` after your `.env`.
- `secrets.env` is made by `node scripts/local-stack.mjs init`. It is git-ignored and never printed. Do not commit or share it.
  It also holds `MAIL_TRIAGE_RUNTIME_PASSWORD` when your `.env` has none; `.env` is never edited. A
  `MAIL_TRIAGE_DATABASE_URL` line in `.env` overrides that password (remove an old owner-login URL; `up` warns).
- `backups/` holds the database dumps that `up` and `backup` write. Git-ignored; the dumps contain your data.
