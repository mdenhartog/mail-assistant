---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-19: End-to-end check (manual, with a test account)

- Layer: e2e
- Contract: a runbook and a script that run the whole flow against a Gmail test account and a test bot; no automated CI run with real accounts.
- Files: `docs/reviews/mail-triage-e2e.md`, `agents/mail-triage/scripts/e2e_seed.py`
- Depends on: U-10, U-13, U-14, U-15, U-16, U-17, U-18
- Parallel: no
- Guardrails: guardrail-pytest
- Criteria:
  1. Given a test mailbox, When a personal request, a newsletter and an automatic notice arrive, Then the first alerts Marco and the other two are only filed (happy; AC-3, AC-4).
  2. Given the alert, When "Reply" is used and confirmed, Then the mail arrives at the test sender and no reminder follows (happy; AC-7).
  3. Given "remind me later" with a short time, When it passes, Then one new alert arrives (happy; AC-9).
  4. Given an injected mail, When processed, Then nothing is sent or deleted (security; AC-19).
  5. Given the whole run, When finished, Then no mail was deleted and the logs contain no body or token (security; AC-2, AC-24).
