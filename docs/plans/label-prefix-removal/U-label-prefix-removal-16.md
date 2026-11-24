---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-16: category-policy: adopt an existing label; keep the reserved names forbidden

- Component: category-policy
- Layer: backend
- Contract: Found while building unit 01: the list rules still refuse a category whose name is an existing label (`name_label_exists`, `adoptable`), which D8 and ADR-0060 point 3 reverse (an existing label is adopted, never refused). The forbidden names stay forbidden: one list of reserved names (`Archive`, `Other`, a first segment `Archive`, and every Gmail system label, compared in any case) is refused as a list category and as a setting name, because `Archive` is often a reserved label elsewhere; the user's decision of 2026-11-24. `validate_list` no longer refuses a name because a label of that name exists; a list category equal to the current name of the "Other" or the archive setting is refused as a clash; the contract cases are updated.
- Files: `packages/category-policy/category_policy/policy.py`, `packages/category-policy/category_policy/__init__.py`, `packages/category-policy/contract/category_cases.json`, tests under `packages/category-policy/tests/`
- Depends on: U-label-prefix-removal-01
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given a list category whose name equals an existing Gmail label, When the list is validated, Then it is accepted and no `name_label_exists` problem is returned (AC 19). (type: happy)
  2. Given the same list validated twice, When compared, Then the result is identical (AC 19). (type: edge)
  3. Given a list category named `Archive`, `Other`, `archive/Taxes` or `OTHER`, When validated, Then it is refused as a reserved name in any case. (type: security)
  4. Given a category equal to the current name of the "Other" or the archive setting, When validated, Then it is refused as a clash (AC 13). (type: error)
  5. Given a category named like a Gmail system label, When validated, Then it is refused in any case (AC 13). (type: security)
  6. Given the one list of reserved names, When the setting names are validated, Then the same list applies, except that the setting may equal its own default (`Other` for "Other", `Archive` for the archive). (type: edge)
  7. Given the contract cases, When the agent and the api suites run them, Then both pass the same file. (type: happy)
  8. Given the package, When searched, Then `adoptable` and `name_label_exists` are gone from the exports. (type: edge)
