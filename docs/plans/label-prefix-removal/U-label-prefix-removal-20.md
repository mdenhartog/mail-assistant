---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-20: Web follows the policy v3 rules: the TypeScript mirror and the messages

- Component: web
- Layer: web
- Contract: Found while building unit 16: `apps/web/src/features/categories/policy.ts` mirrors the policy and reads `category_cases.json` with the `labels` and `adoptable` inputs and the rule `name_label_exists`; `problemText.ts` and `SaveCategories.test.tsx` use the same rule. The mirror takes the `settings` pair, adopts an existing label, reports `name_setting_clash` and passes the shared cases; the e2e support file drops the old archive rules.
- Files: `apps/web/src/features/categories/policy.ts`, `apps/web/src/features/categories/problemText.ts`, `apps/web/src/features/categories/SaveCategories.test.tsx`, `apps/web/e2e/support/categories.ts`, tests beside them
- Depends on: U-label-prefix-removal-16
- Parallel: yes
- Guardrails: guardrail-react, guardrail-typescript, guardrail-vitest-rtl
- Criteria:
  1. Given a category named like an existing label, When validated in the browser, Then it is accepted (AC 19). (type: happy)
  2. Given a category equal to the "Other" or the archive setting, When validated, Then the message for `name_setting_clash` is shown tied to the field (AC 13). (type: error)
  3. Given the shared `category_cases.json`, When `policy.test.ts` runs it, Then every row passes. (type: happy)
  4. Given reserved names and Gmail system labels, When validated, Then they are refused in any case. (type: security)
  5. Given the source, When searched, Then `name_label_exists`, `labels` and `adoptable` appear nowhere in the categories feature. (type: edge)
  6. Given the message texts, When rendered, Then they are plain text and tied to the field with `aria-describedby` (AC 17). (type: a11y)
