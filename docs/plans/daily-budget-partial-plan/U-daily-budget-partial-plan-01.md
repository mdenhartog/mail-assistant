---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-01: The daily budget setting: 500 by default and a bound

- Component: mail-triage agent
- Layer: backend
- Contract: `Settings.daily_model_budget` defaults to 500 and must lie between `BUDGET_RESERVE + CALLS_PER_MAIL` (52) and 1000; a value outside refuses to start with the field name, never the value. The compose default `MAIL_TRIAGE_DAILY_MODEL_BUDGET` becomes 500. The reserve of 50 stays a constant in code.
- Files: `agents/mail-triage/app/settings.py`, `agents/mail-triage/compose.yaml`, `agents/mail-triage/README.md`, tests under `agents/mail-triage/tests/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pydantic, guardrail-pytest, guardrail-compose
- Criteria:
  1. Given a fresh installation, When the settings load, Then the budget is 500 and the reserve is 50 (AC 1). (type: happy)
  2. Given `DAILY_MODEL_BUDGET` of 51 or 1001, When the agent starts, Then settings validation fails and names only the field (SAC-18). (type: security)
  3. Given `DAILY_MODEL_BUDGET` of 52 and of 1000, When the settings load, Then both are accepted (SAC-18). (type: edge)
  4. Given the compose file, When its defaults go through the settings loader, Then the budget is 500 (T-15). (type: edge)
  5. Given the README, When the settings table is read, Then it names 500 and the bound. (type: happy)
