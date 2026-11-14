---
intent: INT-002
feature: web-settings
---

# U-web-settings-51: Limits before the session lookup, IPv6 per /64, bounded counters (R1; challenge fix; RT-03, RT-05, SEC-06)

- Layer: backend
- Contract: `limit("api")` runs before `session` on `GET /api/settings`, `PUT /api/settings`, `GET /api/places`, `GET /api/session` and `POST /auth/logout`; the route inventory requires a limit marker before the session marker on every non-probe route; `client_key` maps an IPv6 address to its /64 and an IPv4 address to itself; the limiter holds at most a configured number of counters per window and refuses new keys over it.
- Files: `backend/app/routers/{session,settings,places}.py`, `backend/app/core/security.py`, `backend/app/clientaddr.py`, `backend/app/limits.py`, `backend/app/limit_guard.py`, `backend/tests/test_route_inventory.py`, `backend/tests/test_limit_guard_api.py`, `backend/tests/test_limits.py`
- Depends on: U-web-settings-24
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pytest
- Criteria:
  1. Given 31 requests a minute without a session to each of the five routes, When sent, Then the 31st gets 429 and no session lookup runs for it (AC-16) (type: security; level: api).
  2. Given 31 requests from 31 addresses of one IPv6 /64, When sent to sign-in, Then the 31st gets 429; two different /64 networks have separate buckets (W-7, W-17) (type: security; level: unit).
  3. Given more distinct keys than the counter bound in one window, When another arrives, Then it is refused and memory stays bounded (type: edge; level: unit).
  4. Given the route inventory, When a route has the session marker without a limit marker before it, Then the test fails naming it (type: security; level: unit).
