# The local week-test stack

The whole web-settings feature runs in Docker on this computer for a week of testing and tuning, with the real limits
of the spec and TLS everywhere. Nothing is published beyond `127.0.0.1` (ADR-0037, decision D-22). Production is not part
of this.

What runs (compose project `mail-assistant`, profile `local`): `db` (TLS only), `mail` (a catcher that takes mail over
STARTTLS only), `mail-triage-migrate` (a one-shot job), `mail-triage` (the agent: Telegram, Gmail and the model from your
`.env`, `ENVIRONMENT=production`, `DATABASE_SSL=verify-full`), `api`, `web` and `edge`. `mail-triage-consent` is a one-shot
service of the same profile that only `node scripts/local-stack.mjs consent` starts (see "Gmail consent").

| What | Where |
| --- | --- |
| The settings page | <https://mail-assistant.localhost:8443> |
| The sign-in codes (the mail catcher) | <http://127.0.0.1:8025> |
| The database (loopback only) | `127.0.0.1:5432` |

## Prerequisites

- Docker with Compose 2.24.0 or newer (the script passes three `--env-file` flags and checks the version; 2.24 is the
  conservative minimum, older versions may work).
- Node 22 or newer, `bash` and `openssl` on the path. On Windows use Git for Windows (Git Bash) and run the script from
  Git Bash or PowerShell with `C:\Program Files\Git\bin` in the path. If `bash` is another program (WSL), set
  `LOCAL_STACK_BASH` to the full path of Git's `bash.exe`.
- Your `.env` (copy of `.env.example`) holds `POSTGRES_PASSWORD` and the Telegram, Gmail and model settings. `up` checks
  that `POSTGRES_PASSWORD` and `MAIL_TRIAGE_RUNTIME_PASSWORD` exist in `.env` or in `deploy/local/secrets.env` (names only,
  it never prints a value) and stops, before any docker call, naming the key that is in neither.
- `MAIL_TRIAGE_RUNTIME_PASSWORD` (the password of the least-privilege database role, ADR-0025): when your `.env` has none,
  `init` writes a fresh random one into `deploy/local/secrets.env`. The script never edits `.env` and never overwrites a value.
- A `MAIL_TRIAGE_DATABASE_URL` entry in `.env` overrides the generated role password in compose (the default URL is built
  from the runtime password). If `.env` still has an old owner-login URL, remove it. `up` prints one `WARNING` line (the
  name only) when `.env` defines `MAIL_TRIAGE_DATABASE_URL` or `MAIL_TRIAGE_DATABASE_OWNER_URL`, because that bypasses the role.
- The checkout runs on branch `local/stack`, which tracks `origin/main`.

## First start

1. `node scripts/local-stack.mjs init` makes the private CA and the certificates (`deploy/prod-like/certs/`) and writes
   `deploy/local/secrets.env` with fresh random keys and passwords, plus `WEB_USERNAME=marco` and
   `WEB_EMAIL_ADDRESS=marco@example.test` (change them with `--username` and `--email` on the first run, or edit the file).
   Running it again changes nothing. Values in `secrets.env` win over the same names in `.env`
   (the order compose gets is `.env`, `stack.env`, `secrets.env`; the later file wins).
2. `node scripts/local-stack.mjs trust-ca` prints how to trust `ca.crt`. It changes nothing itself:
   - Edge and Chrome (Windows): `certutil -user -addstore Root "<path>\ca.crt"`, then confirm the Windows dialog.
     Restart the browser.
   - Firefox: Settings, Privacy & Security, Certificates, View Certificates, Authorities, Import, choose `ca.crt`, tick
     "Trust this CA to identify websites".
3. `node scripts/local-stack.mjs up` does, in order: start `db` and `mail`; if the database volume exists, a backup
   (a failing backup stops everything); the migration (`run --rm --build mail-triage-migrate`); then
   `up -d --build --wait --no-deps` for `mail-triage`, `api`, `web` and `edge`.
4. Open <https://mail-assistant.localhost:8443>. The code mail appears in <http://127.0.0.1:8025>.

Other commands: `consent` (below), `status` (containers and when the certificates end), `logs [service] [--follow]`, `backup`, `down`.
`down` stops the containers and never removes a volume; your data stays in `mail-assistant_db-data`.

## Gmail consent

The agent reads and sends Gmail with a refresh token that is stored encrypted (with `MAIL_TRIAGE_TOKEN_ENCRYPTION_KEY`, in the
container `TOKEN_ENCRYPTION_KEY`). The first start has no token, and the agent stops with exit code 3. A token is also useless
after a new encryption key: the old one cannot be decrypted, and the agent stops with exit code 3 and the message "the stored
Gmail token cannot be decrypted with the current TOKEN_ENCRYPTION_KEY: run node scripts/local-stack.mjs consent". In both
cases do the consent once:

1. In the Google client (Google Cloud console, Credentials, the OAuth client of `GOOGLE_CLIENT_ID`) the redirect address
   `http://127.0.0.1:8765/callback` must be registered, exactly that text (loopback address, not `localhost`, port 8765).
2. `node scripts/local-stack.mjs up` if the database is not running (the agent may stop afterwards; the database is enough).
3. `node scripts/local-stack.mjs consent`. It checks that the database runs and that `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET` and `MAIL_TRIAGE_TOKEN_ENCRYPTION_KEY` exist (names only), builds the image when needed and runs the
   one-shot service `mail-triage-consent`. It prints one address: open it in the browser on this computer and grant access.
   Google then sends the browser to `http://127.0.0.1:8765/callback`; the port is published on the loopback of this computer
   only, and the server inside the container listens for that one request, for at most 5 minutes (state and PKCE are checked).
4. The refresh token goes into the encrypted token store and replaces the old row (there is one row; the old, unreadable
   value is never read). Nothing secret is printed.
5. `node scripts/local-stack.mjs up` again: the agent starts with the new token.

With a new encryption key nothing else needs to happen: the old token is lost, the consent makes a new one with the new key.
If you change the key again later, repeat the consent.

## Update

```text
git pull
node scripts/local-stack.mjs up
```

`up` makes a backup first, runs the migration, rebuilds the images that changed and recreates what changed.

## Week-test checklist

Write down what feels wrong; those are the things to tune.

- Sign in: request a code, read it in the catcher, sign in. Try a wrong username (the answer must look the same).
- Wrong codes: enter wrong codes until the attempts run out (5 per code). Do you get the Telegram alert? Is the wording clear?
- Lock and unlock: use the lock button of the Telegram notice or `/web_lock`; sign-in must stop. `/web_unlock` allows it again.
- Telegram notices and Undo: change a setting in the page; the notice must arrive within the notice interval. Press Undo
  and check that the earlier values return. Press "Undo and lock web sign-in" and check both.
- Quiet hours, both ways: change the quiet hours in the page, then in Telegram, and back. Check that each side sees the change.
- Conflict wording: change the same setting on the page and in Telegram, save the stale one, and read the message.
- Session expiry: leave a session idle (the idle time of the spec) and use it again; check the message and the way back in.
- Restore after expiry (U-47, when merged) and reset (U-45, U-46, when merged).
- Limits (the real ones: 30 requests a minute, 60 s between codes, 5 codes an hour, 5 attempts, 10 open and 20 an hour
  per client): hit each and read the answer. Too tight or too loose? Tune in `.env` with `API_RATE_LIMIT_PER_MINUTE`,
  `API_RESEND_COOLDOWN_SECONDS`, `API_CODES_PER_HOUR`, `API_MAX_ATTEMPTS`, `API_OPEN_LOGIN_REQUESTS_PER_CLIENT` and
  `API_LOGIN_REQUESTS_PER_CLIENT_PER_HOUR`, then `up`. A tuned value is a proposal for the spec, not a change of it.
- The notice interval: `API_NOTICE_INTERVAL_MINUTES` must equal `MAIL_TRIAGE_POLL_INTERVAL_SECONDS` in whole minutes, rounded up.

## Certificates expire after 30 days

`node scripts/local-stack.mjs status` shows the end date. To renew: `node scripts/local-stack.mjs init --renew-certs`
(certificates only; secrets stay), `trust-ca` again (a new CA), then `node scripts/local-stack.mjs up --recreate` so that
`db`, `mail`, `edge` and the others read the new files.

## Roll back

Take the dump you want from `deploy/local/backups/` (every `up` writes one; they hold your data and are git-ignored).
In Git Bash:

```bash
git checkout <the commit or tag to go back to>     # if the code must go back too
node scripts/local-stack.mjs down
docker compose -p mail-assistant --profile local up -d --wait db
docker compose -p mail-assistant exec -T db psql -U app -d postgres -c "DROP DATABASE app WITH (FORCE)" -c "CREATE DATABASE app OWNER app"
docker compose -p mail-assistant exec -T db psql -U app -d app < deploy/local/backups/<timestamp>.sql
node scripts/local-stack.mjs up
```

The database roles live in the server, not in the dump, and stay as they are.

## Stop

`node scripts/local-stack.mjs down`. To start again: `up`. Removing the data (`docker volume rm`) is a deliberate step
that this script does not offer.
