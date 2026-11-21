---
intent: INT-008
feature: label-structure
---

# U-label-structure-06: Remove the automatic plan (R1)

- Component: mail-triage
- Layer: backend
- Contract: the debounce build after a list change and the first-start plan of ADR-0046 are removed (`usecases/resort_build.py` trigger, `plan_debounce_minutes`, the first-start check); a list change never starts a plan; the settings, wiring, docs and chart values that name them are removed.
- Files: `agents/mail-triage/app/usecases/resort_build.py`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/app/settings.py`, `agents/mail-triage/app/wiring.py`, `deploy/` values that name the debounce (platform follow-up note), tests in `agents/mail-triage/tests/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given a list change (by hand, by upload or by Undo), When the debounce time has passed, Then no plan is built and no mail moves. (type: happy)
  2. Given a first start with no plan, When the agent runs, Then no plan is built. (type: happy)
  3. Given a `scheduled` or `applying` plan, When the list changes, Then it still finishes (D12 only removes new automatic plans). (type: edge)
  4. Given the removed setting is still in an environment, When the agent starts, Then it starts and ignores it. (type: edge)
