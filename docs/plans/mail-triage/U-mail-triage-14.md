---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-14: Reply flow with confirmation

- Layer: backend (use case)
- Contract: `start_reply(alert_id, text)`, `confirm(draft_id, token)`, `cancel(draft_id)`.
- Files: `app/usecases/reply.py`, `tests/usecases/test_reply.py`
- Depends on: U-02, U-06, U-09, U-11
- Parallel: no
- Guardrails: guardrail-telegram, guardrail-gmail
- Criteria:
  1. Given Marco's reply text, When `start_reply` runs, Then a draft is stored and shown with recipient, subject, body and Send, Edit, Cancel, and nothing is sent (happy; AC-6, AC-17).
  2. Given the shown draft, When Marco confirms, Then the exact stored text is sent once to the `From` address in the thread and the alert is `closed` (happy; AC-7).
  3. Given Cancel, When pressed, Then nothing is sent and the alert returns to `open` (happy; AC-8).
  4. Given Edit, When pressed and new text arrives, Then a new draft replaces the old one and the old confirmation no longer works (security; AC-20).
  5. Given a confirmation that was already used, expired or issued for another draft, When pressed, Then nothing is sent (security; AC-20).
  6. Given the draft hash no longer matches the stored text, When confirming, Then nothing is sent (security; AC-20).
  7. Given an automatic or list sender, When a reply is started, Then Marco is told it cannot be replied to and nothing is created (security; AC-29).
  8. Given each step, When done, Then an audit record is written without a body (security; AC-22).
