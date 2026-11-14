---
intent: INT-002
feature: web-settings
---

# U-web-settings-67: Digest domain separation, IPv6 event class (R1; challenge round 2; SEC2-07, SEC2-08)

- Layer: backend
- Contract: the client digest uses its own derived subkey (`HMAC(key, b"client-key")`) so no username can collide with a client digest; `client_class` classifies a `/64` key as `ipv6`.
- Files: `backend/app/auth/request_code_rules.py`, `backend/app/auth/event_rules.py`, `backend/tests/auth/test_request_code_rules.py`, `backend/tests/auth/test_event_rules.py`
- Depends on: U-web-settings-64, U-web-settings-63
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given the username `client:10.0.0.5`, When hashed, Then `username_key` differs from `client_hash` of `10.0.0.5` (type: security; level: unit).
  2. Given an IPv6 `/64` key, When classified, Then the class is `ipv6` (type: edge; level: unit).
  3. Given the mutation gate, When both modules are mutated, Then survivors stay at 0 (type: edge; level: unit).
