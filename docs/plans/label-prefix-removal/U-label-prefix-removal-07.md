---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-07: Gmail label delete adapter: delete by id with the filter, type and spam/trash checks

- Component: mail-triage agent
- Layer: backend
- Contract: `adapters/gmail_label_delete.py`: `read_label(id)` returns type, counts and children; `labels_in_filters()` returns every id in `addLabelIds` of the user's Gmail filters; `has_mail_including_trash(id)` runs `messages.list(labelIds=[id], includeSpamTrash=true, maxResults=1)`; `delete(id)` re-reads the label and refuses unless the checks hold, then deletes by id and nothing else.
- Files: `agents/mail-triage/app/adapters/gmail_label_delete.py`, `agents/mail-triage/app/usecases/ports.py`, `agents/mail-triage/tests/fakes/fake_gmail.py` (it still has `ASSISTANT_PREFIX` and a `label:assistant` query matcher that must go), `agents/mail-triage/tests/adapters/test_gmail_reflection.py` (add `delete_label` to `ALLOWED_METHODS`), tests under `agents/mail-triage/tests/adapters/`
- Depends on: U-label-prefix-removal-04
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-python, guardrail-pytest
- Criteria:
  1. Given an empty user label, When delete is called, Then Gmail receives one delete by that id (AC 7). (type: happy)
  2. Given a label with one mail, When delete is called, Then it is refused and Gmail is not called (AC 8). (type: security)
  3. Given a label whose only mail is in trash or spam, When delete is called, Then it is refused (AC 22). (type: security)
  4. Given a system label such as `INBOX`, `SENT` or `CATEGORY_PERSONAL`, When delete is called, Then it is refused even if empty (AC 10b). (type: security)
  5. Given a label that a Gmail filter adds, When delete is called, Then it is refused (AC 21). (type: security)
  6. Given an unclear answer or any error from Gmail, When delete is called, Then the label counts as not empty and is kept. (type: error)
  7. Given a mail injected between the final read and the delete, When tested, Then the re-check and delete are adjacent calls and the outcome is recorded (AC 30). (type: edge)
  8. Given the fake Gmail, When used, Then it supports the counts, `type`, nested names, a case-insensitive 409, 403 and 429 injection and a mail injected between calls. (type: happy)
