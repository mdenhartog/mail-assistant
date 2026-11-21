---
intent: INT-008
feature: label-structure
---

# U-label-structure-34: The web app round-trips the v2 list fields

- Component: web
- Layer: web
- Contract: the api (unit 11) requires `kind`, `notify`, `senders[]` and `generalInstructions` on `PUT /api/categories`; the web app still sends the v1 body, which the api now refuses with a 422, so saving would break on `main`. The api client types come from the OpenAPI document (regenerate them), the categories hooks carry the four fields from `GET` through the form state and back into `PUT` untouched, a new category defaults to `kind` topic, no tick, no senders; no new screen or control: the nested list, kinds, senders and ticks are units 15 and 16. This unit lands in the same pull request as units 11 and 33.
- Files: `apps/web/src/api/categories/` (types, api, queries), `apps/web/src/features/categories/` (form state mapping), the web tests and `apps/web/e2e/categories.spec.ts` (and its support) that send or read a list
- Depends on: U-label-structure-11
- Parallel: yes
- Guardrails: guardrail-typescript, guardrail-react, guardrail-tanstack-query, guardrail-vitest-rtl, guardrail-playwright
- Criteria:
  1. Given a list with kinds, ticks, senders and general instructions from the api, When the user edits a name or description and saves, Then the body sent back carries those four fields unchanged. (type: happy)
  2. Given a new category, When it is added and saved, Then it is sent with kind topic, no tick and no senders. (type: happy)
  3. Given the OpenAPI document, When the client types are generated, Then they match it and the types check passes. (type: happy)
  4. Given a 422 with the new problem shape (`position`, `otherIndex`, fields `senders` and `instructions`), When the page shows it, Then the existing field messages still work and an unknown field shows the generic sentence. (type: error)
  5. Given the end-to-end journey of the categories page against the prod-like stack, When it runs, Then it passes with the v2 body. (type: happy)
