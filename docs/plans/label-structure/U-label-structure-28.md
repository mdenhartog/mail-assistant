---
intent: INT-008
feature: label-structure
---

# U-label-structure-28: The agent follows the policy v2 name rules

- Component: mail-triage
- Layer: backend
- Contract: `is_category_label` in `adapters/gmail_resort.py` stops keeping its own copy of the name rules and uses `category-policy` v2: `Assistant/<name>` where the name is nested per segment, the first segment is not "Archive" or "Other", no empty segment, no `..`, the whole label at most 225 characters. The agent test `test_category_label_contract.py` runs the shared contract cases of unit 02 against it. This unit exists because unit 02 rebuilds the shared rules and the agent test of the shared cases would otherwise fail on `main`; it lands in the same pull request as unit 02.
- Files: `agents/mail-triage/app/adapters/gmail_resort.py`, `agents/mail-triage/tests/adapters/test_category_label_contract.py`, tests of the label sync that name the old rule
- Depends on: U-label-structure-02
- Parallel: yes
- Guardrails: guardrail-python, guardrail-gmail, guardrail-pytest
- Criteria:
  1. Given `Assistant/Huis/Energie` and a three-level path, When checked, Then they are category labels. (type: happy)
  2. Given a first segment "Archive" or "Other", an empty segment, `..`, a leading or trailing `/`, or a label of 226 characters, When checked, Then it is not a category label. (type: error)
  3. Given the shared contract cases, When the agent test runs, Then every `label` row passes. (type: happy)
  4. Given the existing label sync tests, When the agent suite runs, Then they pass (the old one-level assumption is replaced in the tests that named it). (type: edge)
  5. Given no copy of the rules in the agent, When the code is read, Then `is_category_label` calls `category-policy`. (type: edge)
