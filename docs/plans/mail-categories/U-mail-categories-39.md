---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-39: The plan build works in slices so the mail cycle and the heartbeat go on

- Component: agents/mail-triage
- Layer: backend
- Release: R2
- Contract: one run of the plan build looks at no more than `BUILD_SLICE` mails (20) and then pauses like it does when the budget is used up; the next cycle goes on from the stored cursor. The cap, the order, the budget rules, the replacement by a newer list and the single "plan ready" notice stay as they are (ADR-0051). A build of fewer mails than the slice is ready in one run.
- Files: agents/mail-triage/app/usecases/resort_build.py, agents/mail-triage/tests/test_resort_build_slices.py, agents/mail-triage/tests/resort_build_support.py, docs/memory/decisions/ADR-0051-plan-build-in-slices.md
- Depends on: U-mail-categories-14
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-llm
- Criteria:
  1. Given 25 mails and a slice of 10, When the build runs three times, Then the runs check 10, 20 and 25 mails, the plan is ready after the third, every mail is judged once and one notice is sent (type: happy)
  2. Given exactly as many mails as the slice, When the build runs twice, Then the first run makes the plan ready and the second does nothing (type: edge)
  3. Given fewer mails than the slice, When the build runs, Then the plan is ready in that run (type: edge)
  4. Given the normal slice, Then it is small enough for the 180 seconds of the heartbeat (type: ops)
