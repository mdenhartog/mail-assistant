---
intent: INT-008
feature: label-structure
---

# U-label-structure-29: The api follows the policy v2 name rules and limits

- Component: api
- Layer: backend
- Contract: the existing category list endpoints (`backend/app/categories_models.py`, `categories_write.py`) keep working on top of `category-policy` v2: nested names are accepted, the limits are 1 500 characters for a description and 100 categories, the problem codes are the new ones (`name_segment_empty`, `name_segment_too_long`, `name_label_too_long`, and the others of unit 02), and the response mapping and the OpenAPI example use them. No new fields: kinds, senders and ticks come in unit 11. This unit lands in the same pull request as unit 02.
- Files: `backend/app/categories_models.py`, `backend/app/categories_write.py`, `docs/api/openapi.json` (problem codes), `backend/tests/test_categories_api.py` and the other backend tests that name the old rules
- Depends on: U-label-structure-02
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-pytest
- Criteria:
  1. Given a nested name such as `Huis/Energie`, When the list is saved, Then it is accepted. (type: happy)
  2. Given a description of 1 500 characters, Then it is accepted; one more, Then 422 with the new problem code. (type: edge)
  3. Given 100 categories, Then they are accepted; 101, Then 422. (type: edge)
  4. Given a segment of 41 characters, an empty segment or a label of 226 characters, When saved, Then 422 names the new rule and field. (type: error)
  5. Given the shared contract cases, When the api tests run, Then every case passes. (type: happy)
  6. Given the backend suite, When it runs, Then it is green and no test names a removed rule. (type: edge)
