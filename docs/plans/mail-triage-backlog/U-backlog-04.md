---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-04: Gmail lists unread inbox mail before a cut-off

- Layer: backend (adapter)
- Contract: `GmailReader.list_unread_before(cutoff: datetime) -> list[str]`: ids of mails with labels INBOX and UNREAD, query `before:<epoch seconds> -in:sent`, newest first (Gmail's own order), all pages. Read-only; no new scope. Mails carrying the agent's own `SENT` label are left out (`OWN_MAIL`).
- Files: `app/adapters/gmail_read.py`, `tests/adapters/test_gmail_read.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-api-client
- Criteria:
  1. Given a cut-off, When the list is requested, Then the request uses labels INBOX and UNREAD and a `before:` query in epoch seconds (type: happy; AC-B1).
  2. Given two result pages, When the list is requested, Then the ids of both pages come back in Gmail's order (type: happy; AC-B9).
  3. Given a mail with the `SENT` label in the result, When the list is requested, Then it is not returned (type: security; AC-B2).
  4. Given a rate-limit error on a page, When the list is requested, Then it is retried with backoff like other reads (type: error).
  5. Given no matching mail, When the list is requested, Then an empty list is returned (type: edge).
  6. Given the wrapper, When its public methods are inspected, Then it still has no trash, delete or spam operation (type: security; AC-B3, SC-14).
