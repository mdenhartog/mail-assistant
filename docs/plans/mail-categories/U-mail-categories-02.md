---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-02: category-policy package

- Component: category-policy
- Layer: backend
- Release: R1
- Contract: `category_policy`: `normalise_name(raw)`, `validate_category(name, description, existing, labels)`, `validate_list(list)`, `label_for(name)`, `DECISIONS`, limits (1-40 code points, 500 description, 50 categories, 'Other' and 'Archive' reserved); `contract/category_cases.json` run by agent and api.
- Files: packages/category-policy/category_policy/*.py, packages/category-policy/contract/category_cases.json, packages/category-policy/tests/*, packages/category-policy/pyproject.toml
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-pydantic
- Criteria:
  1. Given a name with surrounding spaces or other letter case, When normalised, Then trim, NFKC and case folding make look-alikes and case variants equal (AC-2) (type: happy)
  2. Given an empty name, a 41-code-point name, a name with `/`, a control or format character, Then each is refused with its own rule (AC-2) (type: error)
  3. Given 'Other' or 'Archive' also as a look-alike after NFKC, Then the name is refused (AC-2, MC-16) (type: security)
  4. Given a name equal to an existing Gmail label under `Assistant/` that is not on the list, Then it is refused (AC-2) (type: edge)
  5. Given a description of 501 characters or an empty one, Then it is refused; 500 passes (type: edge)
  6. Given 50 and 51 categories, Then 50 passes and 51 is refused with the reason (AC-8) (type: edge)
  7. Given the shared contract file, When run in the package, Then every case passes (the agent and the api run the same file in U-03 and U-04) (type: happy)
  8. Given random Unicode names (property-based), Then validation never raises and equal normalised names collide (type: edge)
