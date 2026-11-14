---
intent: INT-002
feature: web-settings
---

# U-web-settings-23: Places route (R1)

- Layer: backend
- Contract: `GET /api/places?q=` (session, `LimitGuard("api")`) returns up to 5 `{zone, label, utcOffsetMinutes}` and an optional suggestion from `schedule_policy.places.lookup` (same lookup and aliases as Telegram, ADR-0028); the live local time is computed in the browser. This unit makes the route inventory test exact (equals the allow-list).
- Files: `backend/app/routers/places.py`, `backend/tests/test_places_api.py`, `backend/tests/test_route_inventory.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-15
- Parallel: yes (with U-20 to U-22)
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given `q=New York`, When called, Then a hit for `America/New_York` with label and offset (C-7) (type: happy; level: api).
  2. Given `q=Paris`, When called, Then at most 5 labelled hits; `Nwe York` gives the suggestion `New York` (C-7) (type: edge; level: api).
  3. Given the aliases `NYC` and `Wien`, When called, Then the same results as the Telegram lookup (type: edge; level: api).
  4. Given nothing matches, When called, Then an empty list without error (type: edge; level: api).
  5. Given a 65-character `q`, a control character and an emoji, When called, Then 422 for the first two before matching, an empty or valid result for the emoji (C-7) (type: security; level: api).
  6. Given a typed canary place, When logs are captured, Then the query value is in no log line (W-15) (type: security; level: api).
  7. Given no session, When called, Then 401 (AC-2) (type: security; level: api).
  8. Given the response model, When checked, Then only `zone`, `label`, `utcOffsetMinutes` and `suggestion` exist, and the route inventory equals the allow-list exactly (AC-15) (type: security; level: unit).
