---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-06: Gmail send reply

- Layer: backend (adapter)
- Contract: `GmailSender.send_reply(draft: ConfirmedDraft) -> sent_message_id`
- Files: `app/adapters/gmail_send.py`, `tests/adapters/test_gmail_send.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-api-client
- Criteria:
  1. Given a confirmed draft, When sent, Then the mail goes in the same thread with correct `In-Reply-To` and `References` (happy; AC-7).
  2. Given a mail with a `Reply-To` different from `From`, When replying, Then the recipient is `From` unless the draft names another address (security; AC-16).
  3. Given the original has `Auto-Submitted`, `List-Id`, `Precedence: bulk` or a `noreply` sender, When a reply is requested, Then nothing is sent and the caller receives `NotRepliable` (security; AC-29).
  4. Given the authenticated address differs from the requested sender, When sending, Then it refuses (security; guardrail rule).
  5. Given a send call that fails after a timeout, When retried, Then no duplicate is sent (edge; idempotency key on the draft).
  6. Given the module source, When scanned, Then it references no trash, delete or spam method (security; AC-28).
