---
intent: INT-008
feature: label-structure
---

# U-label-structure-18: Archive label: the agent adopts, creates and renames it (R2)

- Component: mail-triage
- Layer: backend
- Contract: the agent reads the archive label name from `list_settings` (ADR-0059): first time set, an existing Gmail label of that name is adopted, else created; a later change renames the existing label by id, waits until no plan is `scheduled` or `applying`, never creates a second archive label and never moves mail into or out of it; the environment setting `ARCHIVE_LABEL` is removed from the agent, compose and Helm; the label allow-list adds the archive label by id.
- Files: `agents/mail-triage/app/settings.py`, `agents/mail-triage/app/adapters/gmail_resort.py`, `agents/mail-triage/app/usecases/list_sync.py`, `agents/mail-triage/app/core/scope.py`, `compose.yaml` and `deploy/` values (platform follow-up note), tests
- Depends on: U-label-structure-05, U-label-structure-17
- Parallel: yes
- Guardrails: guardrail-python, guardrail-gmail, guardrail-pytest
- Criteria:
  1. Given the first time the name is set and an existing Gmail label of that name, When the agent syncs, Then it adopts it; with no such label it creates it. (type: happy)
  2. Given a later change of the name, When the agent syncs, Then it renames the existing label by id and mail in it stays protected. (type: happy)
  3. Given a rename while a plan is `scheduled` or `applying`, When the agent runs, Then the rename waits until the plan is terminal and new mail is still judged meanwhile. (type: edge)
  4. Given the environment variable `ARCHIVE_LABEL`, When the agent starts, Then it ignores it. (type: edge)
  5. Given any Gmail label operation of the feature, When it is called with a name outside `Assistant/` other than the archive label by id, Then it is refused before the call (allow-list reflection test). (type: security)
  6. Given a mail that carries the archive label and a category label, When scoped, Then the archive label wins and the mail is out of scope. (type: edge)
