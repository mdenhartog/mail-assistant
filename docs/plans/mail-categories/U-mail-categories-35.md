---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-35: Filter and sort the plan items by sender

- Component: api
- Layer: backend
- Release: R2
- Contract: the items route of the open plan accepts a sender filter (part of a name or address, case-insensitive, parameterised SQL, length-bounded) and a sort (sender or subject, ascending or descending) next to the existing `from` and `to` category filters; the sender text travels in a POST body, never in a URL, a log line or an error (ADR-0044, AC-30); without filter and sort the answer is unchanged. The OpenAPI document and reference are regenerated.
- Files: backend/app/routers/plan.py, backend/app/plan_models.py, backend/app/plan_repo.py, backend/tests/**, docs/api/**
- Depends on: U-mail-categories-32
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given items from several senders, When a sender text is posted, Then only the items whose name or address contains it, case-insensitively, come back (type: happy)
  2. Given a sort by sender or subject, ascending or descending, Then the page is in that order and paging stays stable (type: happy)
  3. Given no filter and no sort, Then the answer equals today's answer (type: edge)
  4. Given `%`, `_` and quote characters in the sender text, Then they match literally and no SQL is changed (type: security)
  5. Given the canary sender text, Then it is in no URL, log line, error or stored row (type: security)
  6. Given a sender text over the bound or an unknown sort, Then 422 (type: error)
  7. Given no session, a lock or a missing CSRF token, Then the call is refused as the other plan calls are (type: security)
