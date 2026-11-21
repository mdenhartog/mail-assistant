---
intent: INT-008
feature: label-structure
---

# U-label-structure-02: category-policy v2: names, kinds, limits, archive rule, confidence scale

- Component: category-policy
- Layer: backend
- Contract: pure functions and types: `validate_name(name)` per segment (look-alikes of `/` fold, first segment not "Archive" or "Other", whole label at most 225), `Kind` (`topic`, `extra`), the limits (description 1 500, general instructions 4 000, 100 categories), `validate_archive_label(name, categories)`, `confidence_pct(confidence)` (round half up), `at_or_above(confidence_pct, threshold)`; contract cases in `contract/category_cases.json`.
- Files: `packages/category-policy/category_policy/policy.py` (rebuilt), `packages/category-policy/category_policy/kinds.py`, `packages/category-policy/contract/category_cases.json`, tests in `packages/category-policy/tests/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pydantic, guardrail-pytest
- Criteria:
  1. Given `Huis/Energie`, When validated, Then it is accepted and its label is `Assistant/Huis/Energie`. (type: happy)
  2. Given an empty segment, a leading or trailing `/`, a segment over 40 characters, a label of 226 characters, a control or format character, a first segment "Archive" or "Other" or a `/` look-alike (U+2215, U+FF0F), When validated, Then each is refused with its reason (table, one row per rule; 224 and 225 pass). (type: error)
  3. Given a description of 1 500 and general instructions of 4 000 characters, When validated, Then they pass; one more character is refused. (type: edge)
  4. Given a Gmail system label name in any letter case, a name equal to or below a category label, or inside `Assistant/` other than `Assistant/Archive`, When validated as archive label, Then it is refused. (type: error)
  5. Given confidences 0.495, 0.5, 0.795 and 0.8, When converted and compared with 50 and 80, Then the boundary is "at or above" on the rounded value. (type: edge)
  6. Given the contract cases file, When the unit tests run, Then every case passes (the agent and the api run the same file later). (type: happy)
