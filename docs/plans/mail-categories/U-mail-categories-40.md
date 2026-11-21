---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-40: The archive label name is a validated setting

- Component: agents/mail-triage
- Layer: backend
- Release: R2
- Contract: the setting `ARCHIVE_LABEL` (default `Assistant/Archive`) is read and checked at start by the rules of ADR-0052 point 3; an invalid value stops the agent with a clear error that names the rule and not the value.
- Files: agents/mail-triage/app/settings.py, agents/mail-triage/tests/test_settings.py
- Depends on: U-mail-categories-38
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given no value, When the settings load, Then the archive label is `Assistant/Archive` (type: happy)
  2. Given `Bewaard` or `Mail/Done`, Then it is accepted (type: happy)
  3. Given an empty name, a name with an empty path part, `assistant/archive` in another case, a name with a control character, a leading space, `..`, a system label name, `Assistant/Other`, `Assistant/Travel` or more than 225 characters, Then the load fails (type: security)
