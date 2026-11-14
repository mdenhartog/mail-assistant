---
intent: INT-002
feature: web-settings
---

# U-web-settings-64: A full decoy class is invisible, replace by cookie only, limiter keeps room for the owner (R1; challenge round 2; RT2-03, RT2-04, RT2-05)

- Layer: backend
- Contract: when the decoy class is full, a request for an unknown username is answered like any other (200, cookie, no code sent) but no row is stored, so it never refuses where the owner would not (AC-30); a new request replaces a live one only when it carries the same login cookie, never by `client_hash` alone; the limiter, when the counter bound is reached, evicts the oldest keys (or refuses only keys that are new and carry no valid session or login cookie) so many keys cannot refuse the owner; the limiter keys IPv6 per /64 with a second bound per /48.
- Files: `backend/app/auth/login_requests.py`, `backend/app/auth/request_code.py`, `backend/app/limits.py`, `backend/app/clientaddr.py`, `backend/tests/auth/test_decoy_requests.py`, `backend/tests/test_limits.py`
- Depends on: U-web-settings-53, U-web-settings-51
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 100 live decoy rows, When a code is requested for an unknown name and for the configured name from a fresh client, Then status, headers apart from the cookie value and body shape are identical (AC-30) (type: security; level: api).
  2. Given the owner's live request in browser A and another device in the same /64, When that device asks for the configured username without A's cookie, Then A's request is still live; a request with A's cookie replaces it (type: security; level: db).
  3. Given the limiter at its counter bound, When a new key carries a valid session cookie, or a key seen in the previous window arrives, Then it is allowed; 10000 keys from one /48 cannot refuse the owner (type: security; level: unit).
  4. Given the mutation gate, When `limits.py` and `clientaddr.py` are mutated, Then survivors stay at 0 (type: edge; level: unit).
