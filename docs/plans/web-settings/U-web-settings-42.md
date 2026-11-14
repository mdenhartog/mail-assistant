---
intent: INT-002
feature: web-settings
---

# U-web-settings-42: One prod-like CI job, setup project and smoke test (R1; M2)

- Layer: infra
- Contract: one CI job `prod-like` replaces the separate `e2e` and `runtime-role` jobs, in this order: start the database and the mail catcher; run the migrate service with `docker compose run --rm`; `up --wait`; the database and role checks (the 19 forbidden statements of the agent role plus the web role's); the Playwright `setup` project (signs in once with the code read from the catcher and saves the storage state); `smoke.spec.ts` (open `/settings`, save once); then, in U-43, `journey`; then the log-grep script over the logs of `api`, `web`, edge, `db` and `migrate`. The agent is not in the prod-like stack (it needs real Gmail, Telegram and Anthropic credentials).
- Files: `.github/workflows/ci.yml`, `apps/web/e2e/setup.ts`, `apps/web/e2e/smoke.spec.ts`, `scripts/prodlike-checks.sh`, `agents/mail-triage/tests/e2e/test_web_role.py`
- Depends on: U-web-settings-30, U-web-settings-32, U-web-settings-37, U-web-settings-38, U-web-settings-39
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-docker, guardrail-compose
- Criteria:
  1. Given `ci.yml`, When read, Then one job runs the stated sequence and the old `e2e` and `runtime-role` jobs are gone with their checks kept (type: happy; level: ci).
  2. Given the `setup` project, When it runs, Then the allowed user is signed in with the code from the catcher and the storage state is reused (AC-3, AC-7) (type: happy; level: playwright).
  3. Given the smoke test, When it runs at 375 and 1280 px over real HTTPS, Then `/settings` shows the seeded values, a valid change is saved and a reload shows it (AC-1, AC-9) (type: happy; level: playwright).
  4. Given the web role in the running stack, When it reads `mail_item`, `oauth_token` or `settings_change`, runs DDL, or writes a bad `updated_by`, Then SQLSTATE 42501 each (AC-17, W-8) (type: security; level: ci).
  5. Given a successful sign-in and failure paths (a wrong code, a request for an unknown canary username, a refused STARTTLS, a rejected zone), When the logs of `api`, `web`, edge, `db` and `migrate` are grepped, Then none contains the code, `code=`, the canary username, the canary zone, the SMTP password or a cookie value (AC-20, W-15) (type: security; level: ci).
  6. Given the sequence, When the migrate step fails, Then the job fails before `up --wait` and uploads the logs (type: error; level: ci).
  7. Given a failing run, When it ends, Then the Playwright report and the logs are uploaded and the stack is brought down (type: happy; level: ci).
