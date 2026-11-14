---
intent: INT-002
feature: web-settings
---

# U-web-settings-69: No swallowed decoys, and the lock leaves no trace (R1; challenge round 3; ADR-0039 amendment 2; RT3-02, RT3-03)

- Layer: backend
- Contract: the global decoy cap (`open_login_request_cap`, the swallow branch of U-64) is removed; decoy storage stays bounded by the per-client caps (10 open, 20 per hour), the limiter and the one-hour purge, and a decoy is always stored with its own cooldown, hourly count and attempt counter; while the web lock is set a request is still stored (the owner's row with an unmatchable hash like a decoy, so no code can match) and only the mail is skipped, so cooldown, caps and `attemptsLeft` behave the same locked and unlocked (AC-27, AC-30). Rebuild, no flag.
- Files: `backend/app/auth/login_requests.py`, `backend/app/auth/request_code.py`, `backend/app/config.py`, `backend/tests/auth/test_decoy_requests.py`, `backend/tests/auth/test_request_code.py`, `backend/tests/auth/test_login_requests.py`, `backend/tests/test_login_request_limits_config.py`
- Depends on: U-web-settings-68
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 100 live decoy rows from 10 clients, When a fresh client asks twice within 60 s for an unknown name and twice for the configured name and posts one wrong code with each cookie, Then the second answers have the same status and `Retry-After` and the verify answers have the same `attemptsLeft` presence (AC-30) (type: security; level: api).
  2. Given the web lock is set and then lifted, When a random name is requested twice within 60 s in each state and a wrong code is posted with that cookie, Then the answers are the same in both states and no mail is sent while locked (AC-27) (type: security; level: api).
  3. Given many clients, When each stays within its per-client caps, Then no request is swallowed and the table size is bounded by clients times the per-client cap (type: edge; level: db).
  4. Given the settings, When loaded, Then `open_login_request_cap` no longer exists and the chart's forbidden-key list stays consistent with `Settings` (type: edge; level: unit).
