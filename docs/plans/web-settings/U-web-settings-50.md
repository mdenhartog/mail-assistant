---
intent: INT-002
feature: web-settings
---

# U-web-settings-50: Decoy login requests for unknown usernames (R1; release gate; ADR-0038)

- Layer: backend
- Contract: a request for an unknown username creates a decoy login request (same row, `__Host-login` cookie, expiry, attempt counter and cooldown as a real one; no code is sent and no matching hash is stored); verify-code counts attempts and answers `attemptsLeft` for a decoy exactly as for a real request; a wrong-format code is handled the same way for both.
- Files: `backend/app/auth/request_code.py`, `backend/app/auth/verify_code.py`, `backend/app/auth/login_requests.py`, `backend/tests/auth/test_decoy_requests.py`
- Depends on: U-web-settings-17, U-web-settings-18, U-web-settings-24
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given an unknown and a known username, When a code is requested, Then both answers, cookies and cooldowns are the same and only the known one sends a mail (W-2) (type: security; level: api).
  2. Given a decoy request, When wrong codes are posted, Then `attemptsLeft` counts 4, 3, 2, 1 and the fifth kills the request and clears the cookie, as for a real one (type: security; level: api).
  3. Given a decoy request, When any code is posted, Then it is refused with the generic answer and no session is created (type: security; level: api).
  4. Given a wrong-format code on a decoy and on a real request, When posted, Then the two answers have the same shape and number (type: security; level: api).
  5. Given decoys, When requests are counted, Then they use the cooldown, the hourly cap and the in-process limits like real requests and expire with the existing retention (type: edge; level: db).
  6. Given the two paths, When timed over many runs, Then the medians differ by no more than the noise bound set in the test (type: security; level: api).
