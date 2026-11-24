---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-17: Agent mail path follows the managed set: triage and catch-up

- Component: mail-triage agent
- Layer: backend
- Contract: Found while building unit 03: `usecases/triage.py` and `usecases/catchup.py` still call the old `resolve` and import the removed `OTHER_LABEL`. They take the managed set and the "Other" label from the settings (units 03 and 05), classify with `scope.classify(labels, managed)` and file under the list label or the "Other" setting; no prefix, no constant.
- Files: `agents/mail-triage/app/usecases/triage.py`, `agents/mail-triage/app/usecases/catchup.py`, tests under `agents/mail-triage/tests/usecases/`
- Depends on: U-label-prefix-removal-03, U-label-prefix-removal-04
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given a new mail with no fitting category, When triaged, Then it is filed under the "Other" label of the settings by id (AC 12). (type: happy)
  2. Given a new mail in a managed category, When triaged, Then the list label without a prefix is added and nothing else changes (AC 1, 2). (type: happy)
  3. Given a mail that only carries `Amerika`, When the catch-up looks at it, Then it is left alone (AC 3). (type: security)
  4. Given a mail with two topic labels, When classified, Then it is `UNCLEAR` as before. (type: edge)
  5. Given the source, When searched, Then `OTHER_LABEL` and `LABEL_PREFIX` appear in neither module. (type: edge)
  6. Given the existing triage and catch-up behaviour (urgency, alerts, budget), When run on the fake Gmail, Then the outcomes are unchanged apart from the label names. (type: edge)
