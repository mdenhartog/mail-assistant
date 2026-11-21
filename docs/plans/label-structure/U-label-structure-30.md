---
intent: INT-008
feature: label-structure
---

# U-label-structure-30: The web app follows the policy v2 name rules

- Component: web
- Layer: web
- Contract: the TypeScript copy of the rules in `apps/web/src/features/categories/policy.ts` follows `category-policy` v2 (per-segment name rules, `/` allowed, the limits of 1 500 characters and 100 categories) and passes the same shared cases file (`policy.test.ts`); `problemText.ts` has text for the new problem codes and no text for the removed ones. No new screens: the nested list, kinds and senders come in units 15 and 16. This unit lands in the same pull request as unit 02.
- Files: `apps/web/src/features/categories/policy.ts`, `apps/web/src/features/categories/problemText.ts`, `apps/web/src/features/categories/policy.test.ts`, tests that name the old rules
- Depends on: U-label-structure-02
- Parallel: yes
- Guardrails: guardrail-typescript, guardrail-vitest-rtl
- Criteria:
  1. Given the shared contract cases, When `policy.test.ts` runs, Then every case passes. (type: happy)
  2. Given a nested name, When validated in the form, Then it is accepted. (type: happy)
  3. Given a segment of 41 characters, an empty segment or a label of 226 characters, When validated, Then the form shows the new problem text. (type: error)
  4. Given a description of 1 500 characters and 100 categories, When validated, Then they pass; one more is refused. (type: edge)
  5. Given the old problem codes, When the code is read, Then none remains and `problemText.ts` covers every code of the policy. (type: edge)
