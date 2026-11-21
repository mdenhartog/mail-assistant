---
intent: INT-008
feature: label-structure
---

# U-label-structure-21: Api: the sort-again request routes (R2)

- Component: api
- Layer: backend
- Contract: `POST /api/resort-requests` (`{threshold}`, calls `request_resort`; session, CSRF, `Origin`, hourly limit) and `GET /api/resort-requests/latest` (the value the field shows); the OpenAPI schema is updated; the route allow-list gets both paths.
- Files: `backend/app/routers/resort_requests.py`, `backend/app/services/resort_requests.py`, `backend/app/core/security.py` (allow-list), `docs/api/openapi.json`, tests
- Depends on: U-label-structure-11, U-label-structure-20
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-pytest
- Criteria:
  1. Given a threshold of 50 and of 100, When posted, Then a request exists and the response says so. (type: happy)
  2. Given 49, 50.5, "50 ", "abc" or over 100, When posted, Then 422 and no request is made. (type: error)
  3. Given an open plan, When posted, Then 409 with the reason; a double post makes one request. (type: edge)
  4. Given no session, no CSRF token or a foreign `Origin`, Then 403; above the hourly limit, Then 429. (type: security)
  5. Given the first visit, When the latest request is read, Then the field value is 50; later it is the value of the latest request. (type: happy)
