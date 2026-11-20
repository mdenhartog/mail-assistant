---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-19: R2 end-to-end

- Component: web
- Layer: web
- Release: R2
- Contract: Playwright journeys with the fake Gmail: change the list, a plan appears, review, approve, apply, Move back, Cancel and Lock; first plan at the first R2 start; canary scan; user acceptance of AC-45 in the release checklist.
- Files: apps/web/e2e/review.spec.ts, docs/release/mail-categories-r2.md
- Depends on: U-mail-categories-16, U-mail-categories-18, U-mail-categories-22, U-mail-categories-24
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y
- Criteria:
  1. Given a changed list, When the plan is ready and approved, Then the mail moves and Move back restores it (AC-9, AC-13, AC-14, AC-41) (type: happy)
  2. Given an approval above the threshold, Then the move waits and Cancel stops it (AC-42) (type: happy)
  3. Given the viewports and states, Then axe finds nothing (AC-23) (type: a11y)
  4. Given the canary strings, Then sender and subject are in no log, notice or error (AC-30) (type: security)
  5. Given the release checklist, Then it has the sign-off line for AC-45 (type: happy)
