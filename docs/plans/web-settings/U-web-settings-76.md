---
intent: INT-002
feature: web-settings
---

# U-web-settings-76: The Gmail consent runs in the agent container for the local stack (R1; test environment; D-23)

- Layer: infra, tooling, agent
- Contract: `python -m app.consent` takes its bind host from `CONSENT_BIND_HOST` (default `127.0.0.1`; only `127.0.0.1` and `0.0.0.0` are accepted), and the redirect address that the browser and Google see stays `http://127.0.0.1:8765/callback`; state, PKCE, the one-shot server and the 300 second wait are unchanged. The compose profile `local` gets a one-shot service `mail-triage-consent` (the same image definition, hardening, CA mount, database and Google settings as `mail-triage`, shared by YAML anchor, and no Telegram or model secret; `CONSENT_BIND_HOST=0.0.0.0` inside the container; `restart: "no"`; port published as `127.0.0.1:8765:8765` only, ADR-0037; after the database is healthy and the migrate job has completed). `node scripts/local-stack.mjs consent` refuses when the database is not running or a Google setting is missing (names only), runs `run --rm --build --service-ports -T mail-triage-consent` with the project name and env files of the stack, passes the terminal through, prints only the Google address (the output of the module) and tells Marco to run `up` again. Saving the token replaces the one row of `oauth_token`. A stored token that cannot be decrypted (a new `TOKEN_ENCRYPTION_KEY`) stops `serve` with exit code 3 and the message "the stored Gmail token cannot be decrypted with the current TOKEN_ENCRYPTION_KEY: run node scripts/local-stack.mjs consent", without a traceback and without a key or token in the log. Documentation: `docs/operations/local-stack.md`, `deploy/local/README.md`, the agent README (exit code 3, `CONSENT_BIND_HOST`).
- Files: `agents/mail-triage/app/consent.py`, `agents/mail-triage/app/wiring.py`, `agents/mail-triage/compose.yaml`, `scripts/local-stack.mjs`, `scripts/local-stack.test.mjs`, `agents/mail-triage/tests/test_consent.py`, `agents/mail-triage/tests/test_token_unreadable.py`, `agents/mail-triage/tests/adapters/test_token_store.py`, `agents/mail-triage/tests/infra/test_local_stack.py`, `agents/mail-triage/README.md`, `docs/operations/local-stack.md`, `deploy/local/README.md`
- Depends on: U-web-settings-73, U-web-settings-75
- Parallel: yes
- Guardrails: guardrail-oauth2-oidc, guardrail-gmail, guardrail-compose, guardrail-docker, guardrail-tls-certificates
- Criteria:
  1. Given no setting, `CONSENT_BIND_HOST=0.0.0.0` or any other value, When the bind host is read, Then it is `127.0.0.1`, `0.0.0.0` or a refusal, and the redirect address is `http://127.0.0.1:8765/callback` in every case (type: security; level: unit).
  2. Given a server bound to `0.0.0.0`, When the browser calls back on the loopback, Then the query is received once, other paths get 404, and without a callback the wait ends with "no redirect arrived in time" (type: edge; level: unit).
  3. Given the compose files, When parsed, Then `mail-triage-consent` is in the profile `local` only, is one-shot, publishes only `127.0.0.1:8765:8765`, has the hardening, the CA mount and the database and Google settings of the agent by anchor, and holds no Telegram or model secret (type: security; level: unit).
  4. Given the database running, When `consent` runs, Then it calls `run --rm --build --service-ports -T mail-triage-consent` with the project name and the three env files, passes the terminal through and says to run `up` (type: happy; level: unit).
  5. Given the database not running, a missing Google setting or extra arguments, When `consent` runs, Then it stops before the one-shot run and names what to do (type: error; level: unit).
  6. Given any outcome, When `consent` ends, Then no value of `.env` was printed (type: security; level: unit).
  7. Given a row sealed with a lost key, When the consent saves with the new key, Then row 1 is replaced and the old ciphertext is never read (type: edge; level: db).
  8. Given an undecryptable stored token, When `serve` loads it, Then it stops with exit code 3 and the message, with no traceback, key or token logged (type: error; level: unit).
  9. Given the authorisation address, When prompted, Then only the instruction and the address are printed, flushed (type: security; level: unit).
  10. Given the docs, When read, Then they name the consent step, the redirect address to register, the new-key case and exit code 3 (type: happy; level: unit).
