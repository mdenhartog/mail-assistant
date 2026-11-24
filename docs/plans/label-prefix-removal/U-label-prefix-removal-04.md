---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-04: Agent adapters: allow-list by managed id and the reflection test

- Component: mail-triage agent
- Layer: backend
- Contract: `gmail_read`, `gmail_resort` and `gmail_apply` add, remove, create and rename labels only for managed ids (create is by list name and adopts an existing label, D8); label names in errors are removed (codes only); the reflection test names every Gmail method the agent may call and allows exactly one delete, by id.
- Files: `agents/mail-triage/app/adapters/gmail_read.py`, `agents/mail-triage/app/adapters/gmail_resort.py`, `agents/mail-triage/app/adapters/gmail_apply.py`, tests under `agents/mail-triage/tests/adapters/`
- Depends on: U-label-prefix-removal-03
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-python, guardrail-pytest
- Criteria:
  1. Given a request to add or remove a label that is not managed, When made, Then `LabelRefused` is raised and Gmail is not called (AC 3). (type: security)
  2. Given a new category whose name equals an existing label with mail, When the label is created, Then the existing label is adopted and its mail is untouched (AC 19). (type: happy)
  3. Given a rename by id of a managed label, When made, Then only that id is patched. (type: happy)
  4. Given a Gmail 409 for a name clash, When logged, Then the log has the status and reason and no label name (AC 29). (type: security)
  5. Given a `LabelRefused` or a Gmail error, When raised, Then the message carries a code and no name (AC 29). (type: security)
  6. Given the reflection test, When it runs, Then the only mutating label call besides add, remove, create and rename is delete by id, and no trash, delete-mail or send exists (AC 11). (type: security)
  7. Given a label deleted by hand while its id is stored, When the agent uses it, Then it is recreated once and the id is updated, with no crash (AC 31). (type: edge)
