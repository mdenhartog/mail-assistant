---
intent: INT-008
feature: label-structure
---

# U-label-structure-22: Plan build v2: pair targets, confidence and the scope (R2)

- Component: mail-triage
- Layer: backend
- Contract: the plan build (ADR-0056) reads a `resort_request`, scans the scope (inbox and `Assistant/` labels; not spam, trash, the archive label, pinned or rejected mail) within the budget share above the reserve, judges each mail (a sender-rule mail at confidence 100 without a model call), and writes an item when the pair (topic, extra) would change, with `confidence_pct`; `core/scope.py::classify` is by kind from the list, so a mail with a topic and an extra label is no longer "unclear".
- Files: `agents/mail-triage/app/usecases/resort_build.py`, `agents/mail-triage/app/core/scope.py`, `agents/mail-triage/app/core/resort_plan.py`, `agents/mail-triage/app/db/pg_resort.py`, tests
- Depends on: U-label-structure-08, U-label-structure-20
- Parallel: yes
- Guardrails: guardrail-python, guardrail-gmail, guardrail-llm, guardrail-pytest
- Criteria:
  1. Given a request, When the build runs, Then it covers the mail in scope and an item exists only where the pair would change. (type: happy)
  2. Given a mail with a topic label and an extra label, When scoped, Then it is in scope and not "unclear". (type: edge)
  3. Given a sender-rule target, When the item is decided, Then no model call is made and the confidence is 100. (type: happy)
  4. Given more than 5 000 mails or an exhausted budget, When the build runs, Then it keeps the newest 5 000, uses only the share above the reserve and continues the next day. (type: edge)
  5. Given spam, trash, the archive label, pinned or rejected mail, When scoped, Then none becomes an item. (type: security)
  6. Given a mail whose text tells the model to answer with confidence 100, When judged, Then the stored confidence is the validated number and the text changes nothing else. (type: security)
