---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-38: A label name that Gmail refuses does not stop the label sync

- Component: agents/mail-triage
- Layer: backend
- Release: R2
- Contract: when Gmail answers HTTP 400 to making a label or renaming one, the adapter raises `LabelNameRejected` (the text of Gmail's answer is dropped). The sync treats it as a problem of that one label: a refused `Archive` is skipped with a warning (it is made as a courtesy, so the run still counts as done); a refused category label counts as failed, the other labels are still made, and the cursor does not move so the run repeats; a refused rename leaves the label with its name and counts as failed. Any other Gmail error (403, 429, 5xx) is raised as before. Logs hold counts only, never a label name or the text of Gmail's answer.
- Files: agents/mail-triage/app/adapters/gmail_resort.py, agents/mail-triage/app/usecases/list_sync.py, agents/mail-triage/tests/test_list_sync_refused.py, agents/mail-triage/tests/fakes/fake_gmail.py
- Depends on: U-mail-categories-37
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given Gmail refuses the name `Archive`, When the sync runs, Then the category labels are made, the run is done (cursor moves) and the warning holds no text of Gmail's answer (type: edge)
  2. Given Gmail refuses `Archive` on a first start, When the sync runs, Then the list is still seeded from the labels (type: edge)
  3. Given Gmail refuses one category label, When the sync runs, Then the other labels are made, that category has no stored label, the run reports one failure, the cursor does not move and the log holds no label name (type: edge)
  4. Given Gmail refuses the new name of a rename, When the sync runs, Then the label keeps its name and the run reports one failure (type: edge)
  5. Given Gmail answers 403 or 429 to making `Archive`, When the sync runs, Then the error is raised and not swallowed (type: regression)
