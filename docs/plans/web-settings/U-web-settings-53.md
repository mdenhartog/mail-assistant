---
intent: INT-002
feature: web-settings
---

# U-web-settings-53: The owner cannot be locked out by decoys, other clients or the cap (R1; challenge fix; ADR-0039; RT-01, RT-04, RT-06, SEC-02)

- Layer: backend, database (migration 0010)
- Contract: `web_auth.login_request` gains `client_hash` (keyed digest of the client key); decoys have their own open cap; a request for the configured username is never refused for decoy rows; open rows and codes per hour are also capped per `client_hash`; a new request replaces a live one only for the same login cookie or the same `client_hash`; every 429 carries the real remaining wait; the hourly cap counts from `created_at` for real and decoy rows alike.
- Files: `agents/mail-triage/migrations/versions/0010_login_request_client.py`, `backend/app/auth/login_requests.py`, `backend/app/auth/request_code.py`, `backend/app/auth/request_code_rules.py`, `backend/app/config.py`, `backend/tests/auth/test_decoy_requests.py`, `backend/tests/auth/test_request_code.py`, `backend/tests/auth/test_login_requests.py`
- Depends on: U-web-settings-50, U-web-settings-51
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 100 open decoy requests from one client, When the configured username asks for a code from another client, Then it gets 200 and a mail is sent (AC-16) (type: security; level: db).
  2. Given one client, When it opens more than the per-client number of requests or codes in an hour, Then it is refused while other clients are not (W-7) (type: security; level: db).
  3. Given Marco's live request in browser A, When another client asks for a code for his username, Then A's code still verifies; a request with A's cookie replaces it (type: security; level: db).
  4. Given a refused request, When the 429 is read, Then `Retry-After` equals the real time until the limit frees (type: edge; level: api).
  5. Given five requests then a sixth for a known and an unknown username at identical times, also when the mailer fails, When answered, Then status and `Retry-After` are identical (AC-30) (type: security; level: api).
  6. Given migration 0010, When run up, down and up, Then it is reversible and the web role gets only the grants it needs (type: edge; level: db).
