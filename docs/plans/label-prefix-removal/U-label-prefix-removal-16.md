---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-16: category-policy: adopt an existing label and allow the names Other and Archive in the list

- Component: category-policy
- Layer: backend
- Contract: Found while building unit 01: the list rules still refuse a category whose name is an existing label (`name_label_exists`, `adoptable`) and the reserved names `Other` and `Archive`. D8 and ADR-0060 point 3 say an existing label is adopted, never refused, and the names of "Other" and the archive are settings. `validate_list` no longer refuses a name because a label of that name exists; a list category named like the "Other" or the archive setting is refused by the setting-name rule (clash), not by a reserved list name; the contract cases are updated.
- Files: `packages/category-policy/category_policy/policy.py`, `packages/category-policy/category_policy/__init__.py`, `packages/category-policy/contract/category_cases.json`, tests under `packages/category-policy/tests/`
- Depends on: U-label-prefix-removal-01
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given a list category whose name equals an existing Gmail label, When the list is validated, Then it is accepted and no `name_label_exists` problem is returned (AC 19). (type: happy)
  2. Given the same list validated twice, When compared, Then the result is identical (AC 19). (type: edge)
  3. Given a category named `Other` or `Archive` while the settings use other names, When validated, Then it is accepted; given a category equal to the current name of the "Other" or the archive setting, Then it is refused as a clash (AC 13). (type: error)
  4. Given a category named like a Gmail system label, When validated, Then it is still refused in any case. (type: security)
  5. Given the contract cases, When the agent and the api suites run them, Then both pass the same file. (type: happy)
  6. Given the package, When searched, Then `adoptable` and `name_label_exists` are gone from the exports. (type: edge)
