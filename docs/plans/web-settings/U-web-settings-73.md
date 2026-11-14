---
intent: INT-002
feature: web-settings
---

# U-web-settings-73: The local week-test stack: the whole feature in Docker with the real limits (R1; test environment; D-22)

- Layer: infra, tooling
- Contract: a compose profile `local` runs everything on one computer with the limits of the spec and TLS everywhere, for a week of testing by Marco (nothing is exposed beyond `127.0.0.1`, ADR-0037): `db` (TLS only, through `deploy/prod-like/db-tls.sh`), `mail` (the STARTTLS catcher; its web interface on `127.0.0.1:8025` shows the sign-in codes), `mail-triage-migrate` and `mail-triage` (with `ENVIRONMENT=production` and `DATABASE_SSL=verify-full` against the private CA, Marco's `.env` for Telegram, Gmail and the model), `api`, `web` and `edge` (<https://mail-assistant.localhost:8443>). The e2e limits (rate limit 1000, cooldown 1 s, codes per hour 1000, per-client caps 1000) belong to the e2e runs only: they move out of the service definition into variables that the CI `prod-like` job sets and that default to the spec values, so the `local` profile runs with the real limits (rebuild, no second copy of the services). `scripts/local-stack.mjs` has the commands `init` (makes the private CA and the certificates with `deploy/prod-like/certs.sh`; writes `deploy/local/secrets.env`, git-ignored, with fresh random `APP_CODE_HASH_KEY`, `APP_CSRF_KEY`, `APP_USERNAME_HASH_KEY` (three distinct keys), `WEB_ROLE_PASSWORD`, `MAIL_SMTP_PASSWORD`, and the configured `WEB_USERNAME` and `WEB_EMAIL_ADDRESS` with the defaults `marco` and `marco@example.test`, never overwriting an existing value and never printing a secret), `up`, `down`, `status`, `logs`, `backup` (a `pg_dump` of the database to `deploy/local/backups/`, git-ignored) and `trust-ca` (prints how to trust `ca.crt` in the browser; it changes no trust store itself). `up` runs `backup` first when the database volume exists. Documentation: `docs/operations/local-stack.md` (start, update, stop, where the codes appear, the week-test checklist of things to try and tune, certificates expire after 30 days: how to renew).
- Files: `compose.yaml`, `agents/mail-triage/compose.yaml`, `scripts/local-stack.mjs`, `deploy/local/README.md`, `.gitignore`, `.github/workflows/ci.yml`, `docs/operations/local-stack.md`, `agents/mail-triage/tests/infra/test_local_stack.py`, `backend/tests/test_edge_config.py`
- Depends on: U-web-settings-58, U-web-settings-66, U-web-settings-39
- Parallel: yes
- Guardrails: guardrail-compose, guardrail-docker, guardrail-tls-certificates, guardrail-playwright
- Criteria:
  1. Given the compose files, When parsed, Then the services of the `local` profile are exactly db, mail, mail-triage-migrate, mail-triage, api, web and edge, every published port is bound to `127.0.0.1`, and the `local` profile sets none of the e2e limit overrides (type: security; level: unit).
  2. Given the compose files, When parsed, Then the e2e limits come from variables that default to the spec values (30 a minute, 60 s cooldown, 5 codes an hour, 5 attempts, 10 open and 20 an hour per client) and the CI `prod-like` job sets the raised values (type: edge; level: unit).
  3. Given `local-stack.mjs init` in an empty temp directory, When run twice, Then the secrets file exists with five distinct random values, the second run changes nothing, no secret appears on stdout, and the file is git-ignored (type: security; level: unit).
  4. Given the agent services of the `local` profile, When parsed, Then they run with `ENVIRONMENT=production`, `DATABASE_SSL=verify-full` and the CA mounted read-only, and the dev profile keeps `development` and `disable` (type: security; level: unit).
  5. Given `up` with an existing database volume, When started, Then `backup` runs first and a failing backup stops `up` (type: error; level: unit).
  6. Given the CI `prod-like` job, When it runs, Then the e2e journey still passes with the raised limits set by the job (type: happy; level: ci).
