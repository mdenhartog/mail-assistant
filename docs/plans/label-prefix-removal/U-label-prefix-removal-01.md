---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-01: category-policy v3: names without the prefix, the new name rules and the setting bounds

- Component: category-policy
- Layer: backend
- Contract: `label_for(name)` returns the canonical list name without a prefix; `validate_label_setting_name(name, categories)` checks the names of "Other" and the archive label; constants and checks for the waiting time (5 minutes to 12 hours), the protection period (1 to 30 days) and the retention (7 to 90 days); the contract cases are regenerated.
- Files: `packages/category-policy/category_policy/policy.py`, `packages/category-policy/category_policy/__init__.py`, `packages/category-policy/category_policy/settings.py`, `packages/category-policy/contract/category_cases.json`, tests under `packages/category-policy/tests/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given a list name `Aankopen/Marktplaats`, When `label_for` is called, Then the label is `Aankopen/Marktplaats` and there is no `Assistant/` anywhere (AC 1). (type: happy)
  2. Given names of 255 and 256 characters, a multibyte name, a leading slash, a double slash and a case-only difference, When validated, Then the boundary is enforced as the policy defines (AC 32). (type: edge)
  3. Given the names `other`, `ARCHIVE`, `inbox` and `CATEGORY_PERSONAL` for "Other" or the archive label, When validated, Then they are refused, case-insensitively (AC 13). (type: error)
  4. Given a setting name that equals or lies below a list category, When validated, Then it is refused with a Problem the web app can show. (type: error)
  5. Given the waiting time 4 minutes and 12 hours 1 minute, the protection 0 and 31 days, the retention 6 and 91 days, When validated, Then each is refused; the bounds themselves are accepted (AC 33, 34). (type: edge)
  6. Given the contract cases, When the agent and the api suites run them, Then both pass the same file. (type: happy)
  7. Given the old prefix constant, When the package is searched, Then `LABEL_PREFIX` is no longer exported (ADR-0060). (type: edge)
