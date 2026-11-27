---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-10: The one daily notice and the announced gate

- Component: mail-triage agent
- Layer: backend
- Contract: `usecases/resort_notice.py` and `usecases/resort_apply.py`: the existing "plan ready" message is the one message and says the part number, the counts and, when more mail waits, that the rest continues after this part. One per mailbox and UTC day (a row in `notice_day`, written in the same transaction as the send record), except the notice of an `auto` part with items, which is always sent. A part cannot become `applying` while `announced_at` is empty. Nonces are tied to plan and chat. Counts and fixed words only. A series end by `expired` or `ended` is also announced once with counts only.
- Files: `agents/mail-triage/app/usecases/resort_notice.py`, `agents/mail-triage/app/usecases/resort_apply.py`, `agents/mail-triage/app/usecases/telegram_actions.py`, `agents/mail-triage/app/db/pg_approval.py`, tests under `agents/mail-triage/tests/usecases/`
- Depends on: U-daily-budget-partial-plan-08
- Parallel: yes
- Guardrails: guardrail-python, guardrail-telegram, guardrail-pytest
- Criteria:
  1. Given a part is ready, When the message is sent, Then it holds only counts and fixed words and at most one such message is sent per UTC day (AC 10). (type: security)
  2. Given a part with sure items and no sent notice, When its apply time passes, Then it does not move mail (AC 20, SAC-14). (type: security)
  3. Given a failed send of the notice of an `auto` part, When the next run comes, Then it is sent again before any move (T-12). (type: security)
  4. Given two instances, When both send, Then only one notice is sent (T-12). (type: security)
  5. Given the Cancel button of part 1, When it is pressed after part 2 exists, Then only part 1 is affected or it is refused as used; given a chat that is not allowed or a wrong secret, Then it is refused (SAC-15). (type: security)
  6. Given a series ends by `expired`, When the day changes, Then one counts-only notice says so (AC 16, SAC-12). (type: edge)
  7. Given logs, When a notice is sent, Then no sender, subject, label name or message id is in them (SAC-17). (type: security)
