---
intent: INT-002
feature: web-settings
---

# U-web-settings-63: The lock counts only wrong codes against a live request (R1; challenge round 2; ADR-0039 amendment; SEC2-01, RT2-01)

- Layer: backend (agent unchanged)
- Contract: `verify-code` records `code_refused` only for a well-formed wrong, expired or exhausting code against a login request that exists (real or decoy); a request without a login cookie, with a malformed body, or for a dead, unknown or replaced request records `code_invalid` instead, a kind that never counts towards the alert or the lock and is deduplicated like the other uncounted kinds. The answers to the visitor do not change (AC-30).
- Files: `backend/app/auth/verify_code.py`, `backend/app/auth/event_rules.py`, `backend/tests/auth/test_verify_code.py`, `backend/tests/auth/test_event_rules.py`, `backend/tests/db/test_security_events.py`
- Depends on: U-web-settings-54
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pytest
- Criteria:
  1. Given no login request, When 20 posts arrive from one client without cookie, with body `{}` and with a well-formed code and an unknown cookie, Then the sum of `count` of `code_refused` is 0 and `code_invalid` holds them (W-13) (type: security; level: db).
  2. Given a live login request, When 5 wrong well-formed codes are posted with its cookie, Then the sum of `count` of `code_refused` is 5 (type: happy; level: db).
  3. Given a decoy login request, When wrong codes are posted, Then they count as `code_refused` like for a real one (AC-30) (type: security; level: db).
  4. Given the agent suite, When 50 `code_invalid` events exist, Then no alert and no lock (type: security; level: agent).
