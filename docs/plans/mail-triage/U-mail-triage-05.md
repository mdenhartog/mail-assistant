---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-05: Gmail read and label operations

- Layer: backend (adapter)
- Contract: `GmailReader` with `list_new(history_id)`, `fetch(message_id)`, `ensure_label(name)`, `file(message_id, label)`; no other methods.
- Files: `app/adapters/gmail_read.py`, `tests/adapters/test_gmail_read.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-api-client, guardrail-oauth2-oidc
- Criteria:
  1. Given two pages of history, When `list_new` runs, Then all new inbox mails are returned (happy; guardrail pagination).
  2. Given the agent's own sent mail, When listing, Then it is excluded (security; AC-29).
  3. Given a mail with attachments, When `fetch` runs, Then only headers and the text part are fetched, never an attachment (security; AC-23).
  4. Given a category label, When `file` runs, Then exactly that label is added and `INBOX` is removed and nothing else changes (happy; AC-1).
  5. Given the module source, When scanned, Then it references no trash, delete or spam method (security; AC-2, AC-28).
  6. Given HTTP 429, When a call runs, Then it retries with backoff and then succeeds (error; AC-12).
  7. Given an expired access token, When a call runs, Then it refreshes and continues (edge).
