---
intent: INT-002
feature: web-settings
---

# U-web-settings-62: Test hygiene: no silent skips, structural decoy check (R1; challenge fix; CR-02, CR-05, CR-12)

- Layer: backend, web tests
- Contract: database fixtures fail instead of skip when `CI` is set and skip only for Docker-unavailable errors; a CI step asserts a minimum number of database tests ran; the decoy equality test compares the recorded database and mail-queue steps of both paths and the wall-clock comparison runs only in the mutation workflow behind a marker; the contract fixture filters its cases before generating; the journey uses web-first assertions instead of `setTimeout`.
- Files: `backend/tests/db/conftest.py`, `backend/tests/db/test_database_tls.py`, `backend/tests/db/test_contract_fixture.py`, `backend/tests/auth/test_decoy_requests.py`, `.github/workflows/ci.yml`, `apps/web/e2e/journey.spec.ts`
- Depends on: U-web-settings-53
- Parallel: no
- Guardrails: guardrail-pytest, guardrail-playwright
- Criteria:
  1. Given `CI` is set and the container cannot start, When the database tests run, Then the run fails (type: security; level: unit).
  2. Given the backend job, When it ends, Then it fails if fewer than the stated number of database tests ran (type: security; level: ci).
  3. Given a known and an unknown username, When requested, Then the recorded steps are equal (AC-30) (type: security; level: api).
