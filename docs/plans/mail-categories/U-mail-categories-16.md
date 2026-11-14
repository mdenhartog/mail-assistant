---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-16: Approvals, Cancel and Lock in Telegram

- Component: mail-triage
- Layer: backend
- Release: R2
- Contract: `usecases/approval_notice.py`: 'N mails move at T' notice with Cancel and Lock (nonce-bound `telegram_action`), Cancel and Lock cancel `scheduled` plans, Move back button; Cancel after expiry refused.
- Files: agents/mail-triage/app/usecases/approval_notice.py, agents/mail-triage/tests/test_approval_notice.py
- Depends on: U-mail-categories-07, U-mail-categories-15
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-telegram
- Criteria:
  1. Given an approval above the threshold, Then one notice 'N mails move at T' with Cancel and Lock is sent (AC-42) (type: happy)
  2. Given Cancel before `apply_after`, Then nothing moves and the plan is `cancelled` (AC-42) (type: happy)
  3. Given Cancel after the delay expired, Then it is refused and the notice says so (AC-42) (type: edge)
  4. Given a button pressed twice, late or from another chat, Then nothing changes (AC-48) (type: security)
  5. Given Lock, Then the web lock is set and `scheduled` plans are cancelled (AC-42, AC-57) (type: security)
