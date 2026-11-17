---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-34: Mutation gate for the INT-004 pure modules

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: the INT-004 pure modules (`policy.py`, `pinned.py`, `scope.py`, `list_text.py`, `approval_text.py`, `resort_plan.py`) are mutated nightly and each scores at least 85 %.
- Files: agents/mail-triage/cosmic-ray-categories.toml, packages/category-policy/cosmic-ray.toml, .github/workflows/mutation.yml, agents/mail-triage/tests/core/**, agents/mail-triage/tests/infra/test_deploy.py
- Depends on: U-mail-categories-02, U-mail-categories-05
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given the nightly workflow, Then every INT-004 pure module is mutated and rated at 85 % (type: happy)
  2. Given a surviving mutant, Then a test kills it or the config documents it as equivalent (type: edge)
  3. Given a gate in a directory, Then the workflow test checks it against its own config (type: edge)
