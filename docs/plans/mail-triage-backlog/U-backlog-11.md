---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-11: End-to-end replay and runbook

- Layer: backend (test) and docs
- Contract: an end-to-end test on the existing real-PostgreSQL harness with fake Gmail, Telegram and Anthropic that replays 2026-11-08: 75 unread mails (some urgent), a budget of 200 and the reserve of 50, over two simulated days with new mail arriving in between. The runbook `docs/reviews/mail-triage-e2e.md` gets a catch-up check (check 9) and `docs/reviews/mail-triage-backlog.md` is created as the review record.
- Files: `tests/db/test_catch_up_end_to_end.py`, `docs/reviews/mail-triage-e2e.md`, `docs/reviews/mail-triage-backlog.md`
- Depends on: U-10
- Parallel: no
- Guardrails: guardrail-pytest
- Criteria:
  1. Given 75 unread old mails and the budget, When the cycles run, Then every old mail has one label and left the inbox within two days and no mail was deleted or sent (type: happy; AC-B1, AC-B3).
  2. Given new mail arriving each cycle, When the catch-up runs, Then every new mail is handled in its own cycle (type: happy; AC-B7, AC-B15).
  3. Given more than five urgent old mails, When it finishes, Then five alerts were sent and the rest sit in the next overview (type: happy; AC-B10).
  4. Given a restart in the middle of the catch-up, When it resumes, Then no mail is processed twice and no second catch-up starts (type: edge; AC-B5).
  5. Given read mail and mail outside the inbox in the fake mailbox, When it finishes, Then none of it changed (type: security; AC-B2).
  6. Given the log output and the audit log, When they are searched for mail text, Then nothing is found (type: security; AC-B13).
