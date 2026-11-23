---
intent: INT-008
feature: label-structure
---

# U-label-structure-39: Api: the review plan shows pairs, confidence, tips and what moved on its own (R2)

- Component: api
- Layer: backend
- Contract: found while starting unit 26: the review-plan routes (`backend/app/routers/plan.py`, `plan_models.py`, `plan_repo.py`) still describe an item as one old and one new category. Additive fields (OpenAPI updated, generated web types regenerated): per item the full nested names of the old and new topic and of the old and new extra label, `confidencePct` and the category's `tip` (plain text, as stored); on the plan the `threshold` it copied and a summary of its sibling `auto` plan of the same request (how many items moved or are scheduled on their own, and how many were skipped); the routes keep reading only the `review` plan for the approve, reject and decision actions; a tip is returned as stored text and never used in any write; the existing approve, decision and move-back contracts do not change.
- Files: `backend/app/plan_models.py`, `backend/app/plan_repo.py`, `backend/app/routers/plan.py`, `docs/api/openapi.json`, `docs/api/reference.md`, `apps/web/src/api/schema.d.ts` (generated only), tests
- Depends on: U-label-structure-21, U-label-structure-23, U-label-structure-24
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a ready `review` plan whose items have pairs, When the items route is read, Then every item carries the full old and new names of the topic and of the extra label (null when there is none). (type: happy)
  2. Given items with a confidence and a tip, When read, Then `confidencePct` and the category's `tip` are returned as plain text. (type: happy)
  3. Given a request whose `auto` plan moved or scheduled items, When the plan is read, Then it carries the threshold and the counts of items that moved on their own, are scheduled and were skipped. (type: happy)
  4. Given a request with no `auto` plan, When read, Then the summary says zero. (type: edge)
  5. Given a stored tip with markup or a link, When read, Then the text is returned unchanged as a string and nothing in the route applies it. (type: security)
  6. Given the approve, decision and move-back routes, When used as before, Then their requests, responses and conflicts are unchanged. (type: edge)
  7. Given the sender and subject of an item, When any route other than the items route answers, Then they are not in the response (unchanged rule of ADR-0047). (type: security)
