---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-41: The protected label follows the setting

- Component: agents/mail-triage
- Layer: backend
- Release: R2
- Contract: the archive label is a required argument of `classify`, `is_archive_label`, `is_category_label`, the Gmail adapter and the label sync, instead of the constant `Archive`. A mail with the label is out of scope and wins over a category label; the adapter refuses to add it to or remove it from mail and creates only that label and labels under `Assistant/`; the sync makes it when missing and goes on when Gmail refuses (ADR-0052).
- Files: agents/mail-triage/app/core/scope.py, agents/mail-triage/app/adapters/gmail_resort.py, agents/mail-triage/app/adapters/gmail_apply.py, agents/mail-triage/app/usecases/list_sync.py, agents/mail-triage/app/usecases/resort_build.py, agents/mail-triage/app/usecases/resort_apply.py, agents/mail-triage/app/usecases/move_back.py, agents/mail-triage/app/wiring.py, agents/mail-triage/tests
- Depends on: U-mail-categories-40
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given the setting `Bewaard`, When a mail carries `Bewaard` and `Assistant/Travel`, Then it is out of scope (type: happy)
  2. Given the default, When a mail carries `Assistant/Archive`, Then it is out of scope and is not a category label (type: happy)
  3. Given the default, When the adapter is asked to add or remove `Assistant/Archive` on a mail, Then it refuses (type: security)
  4. Given a mailbox without the label, When the sync runs, Then the label is made once; given Gmail refuses it, Then the sync goes on and the run is done (type: edge)
  5. Given the allow-list scan of the adapter, Then it still holds (type: security)
