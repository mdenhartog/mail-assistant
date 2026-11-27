---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-07: The watermark cursor and the poison mail

- Component: mail-triage agent
- Layer: backend
- Contract: `adapters/gmail_build.py` scans from an internalDate and message id watermark instead of a message id with a fall-back to the top. When the mark cannot be found the scan continues after the mark's date; if even that cannot be placed it reports `cursor_lost` and never restarts at the top. A mail on which the model fails (refusal or time-out) three times is returned as `unclear` with no further call and the cursor moves past it. The cursor is never logged.
- Files: `agents/mail-triage/app/adapters/gmail_build.py`, `agents/mail-triage/app/adapters/gmail_resort.py`, `agents/mail-triage/app/core/resort_plan.py`, tests under `agents/mail-triage/tests/adapters/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-gmail, guardrail-pytest
- Criteria:
  1. Given part 1 ended at mail M and M was deleted, When the next scan starts, Then it continues after M's date and no mail of part 1 is listed again (SAC-10, AC 19). (type: edge)
  2. Given the mark cannot be placed at all, When the scan starts, Then it returns `cursor_lost` and lists nothing (T-08). (type: security)
  3. Given a mail on which the model fails 3 times, When the build runs again, Then the mail is `unclear`, the cursor moves past it and no further call is spent (SAC-4, AC 18). (type: security)
  4. Given a mail that fails twice and then succeeds, When it is judged, Then the result is used and the attempts are not reset to zero for other mails. (type: edge)
  5. Given logs, When a cursor moves or is lost, Then they hold no message id, no internalDate and no mail text (SAC-17). (type: security)
