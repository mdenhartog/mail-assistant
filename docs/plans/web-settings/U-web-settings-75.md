---
intent: INT-002
feature: web-settings
---

# U-web-settings-75: The local stack supplies a missing runtime password itself (R1; test environment; D-22)

- Layer: tooling
- Contract: `scripts/local-stack.mjs init` also writes `MAIL_TRIAGE_RUNTIME_PASSWORD` (fresh random value, never printed) into `deploy/local/secrets.env` when neither `.env` nor `secrets.env` has it, and `up` accepts the name from either file; it never edits `.env` and never overwrites an existing value. The check reads variable names only and `up` still stops, naming the key, when a required name is in neither file. `docs/operations/local-stack.md` and `deploy/local/README.md` say so, and that a `MAIL_TRIAGE_DATABASE_URL` line in `.env` overrides the generated role password (remove it when it still holds the old owner login).
- Files: `scripts/local-stack.mjs`, `scripts/local-stack.test.mjs`, `agents/mail-triage/tests/infra/test_local_stack.py`, `docs/operations/local-stack.md`, `deploy/local/README.md`
- Depends on: U-web-settings-73
- Parallel: yes
- Guardrails: guardrail-compose, guardrail-pytest
- Criteria:
  1. Given `.env` without `MAIL_TRIAGE_RUNTIME_PASSWORD`, When `init` runs twice, Then `secrets.env` holds one random value, the second run changes nothing and nothing is printed (type: security; level: unit).
  2. Given the name in `.env` only, in `secrets.env` only, or in both, When `up` checks, Then it passes and the existing value is never overwritten (type: edge; level: unit).
  3. Given the name in neither file, When `up` runs, Then it stops before any docker call naming the key (type: error; level: unit).
  4. Given the script source, When searched, Then it never writes to `.env` (type: security; level: unit).
