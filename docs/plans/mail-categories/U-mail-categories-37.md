---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-37: A failed step names the Gmail status and reason in the log

- Component: agents/mail-triage
- Layer: backend
- Release: R2
- Contract: when a step of the run loop fails on a call to the Google API, the warning line carries the HTTP status and the short reason code Google gives (`status=403 reason=forbidden`), so an operator can tell which kind of failure it is. The message of the error is never logged: it can hold a label name or mail text. A failure that is not a Google API error logs the kind only, as before.
- Files: agents/mail-triage/app/runner.py, agents/mail-triage/tests/test_runner.py
- Depends on: U-mail-categories-21
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given a step that fails with a Gmail error of status 403 and reason `forbidden`, When a cycle runs, Then the log names the kind, the status and the reason, and holds neither the error text nor a label name (type: security)
  2. Given a Gmail error without a reason, When a cycle runs, Then only the status is logged (type: edge)
  3. Given a step that fails with another error, When a cycle runs, Then the log names the kind only, as before (type: regression)
