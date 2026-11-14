---
intent: INT-002
feature: web-settings
---

# U-web-settings-60: One cookie builder, current attemptsLeft docs, one retention constant (R1; challenge fix; CR-03, CR-04, CR-10)

- Layer: backend
- Contract: `app/auth/cookies.py` builds and clears every `__Host-` cookie; `client_key` lives next to `clientaddr`; the verify-code description says `attemptsLeft` is present for a real or decoy login request and the generated files are rebuilt; one `LOGIN_REQUEST_RETENTION` constant; expired sessions and login requests are purged on the first request of each hour as well as at start-up.
- Files: `backend/app/auth/cookies.py`, `backend/app/auth/session.py`, `backend/app/auth/request_code.py`, `backend/app/auth/verify_code.py`, `backend/app/routers/auth.py`, `backend/app/startup.py`, `docs/api/openapi.json`, `docs/api/reference.md`, `apps/web/src/api/schema.d.ts`, `backend/tests/auth/test_cookies.py`
- Depends on: U-web-settings-53, U-web-settings-54
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-python, guardrail-pytest
- Criteria:
  1. Given each cookie, When set or cleared, Then it is `__Host-`, Secure, HttpOnly, SameSite=Lax, Path=/ and has no Domain (AC-7) (type: security; level: unit).
  2. Given the generated API files, When regenerated, Then the check passes and the `attemptsLeft` text matches AC-3 (type: edge; level: unit).
  3. Given expired rows and one hour passing (`FakeClock`), When the next request arrives, Then they are purged once (type: edge; level: db).
