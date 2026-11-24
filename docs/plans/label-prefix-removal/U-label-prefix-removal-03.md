---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-03: Agent core: managed labels by id, scope without the prefix and filing labels

- Component: mail-triage agent
- Layer: backend
- Contract: A pure `core/managed.py` holds the managed set (category ids, "Other", archive) by label id with the name as fallback; `scope.classify` decides by managed ids and the inbox; `judgement` files under the list label or the "Other" label; every copy of `LABEL_PREFIX` (`scope`, `judgement`, `overview`) is removed in favour of `category-policy`.
- Files: `agents/mail-triage/app/core/managed.py`, `agents/mail-triage/app/core/scope.py`, `agents/mail-triage/app/core/judgement.py`, `agents/mail-triage/app/usecases/overview.py`, tests under `agents/mail-triage/tests/core/`
- Depends on: U-label-prefix-removal-01
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given a mail that carries a label whose id is managed, When the scope is decided, Then it is in scope (AC 2). (type: happy)
  2. Given a mail with only `Amerika`, which is not managed, When the scope is decided, Then it is out of scope and nothing is planned for it (AC 3). (type: security)
  3. Given a mail in the inbox, When the scope is decided, Then it is in scope as before. (type: happy)
  4. Given a mail with the archive label and a managed label, When decided, Then the archive wins and the mail is out of scope. (type: edge)
  5. Given a hand-renamed managed label whose id is stored, When the scope is decided, Then it is found by id (AC 15). (type: edge)
  6. Given the judgement finds no category, When filed, Then the "Other" label of the settings is used, not a constant. (type: happy)
  7. Given the source, When searched, Then `Assistant/` appears in no agent core module. (type: edge)
