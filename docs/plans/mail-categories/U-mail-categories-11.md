---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-11: R1 end-to-end

- Component: web
- Layer: web
- Release: R1
- Contract: Playwright journeys against the prod-like stack and a fake Gmail container: edit and save the list, rename, add the older category, Archive, notices; spec viewports with 200 % zoom; canary scan of logs.
- Files: apps/web/e2e/categories.spec.ts, deploy/ (fake Gmail service for the prod-like profile), docs/release/mail-categories-r1.md
- Depends on: U-mail-categories-07, U-mail-categories-09, U-mail-categories-10, U-mail-categories-20, U-mail-categories-21, U-mail-categories-23, U-mail-categories-25
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y
- Criteria:
  1. Given the stack, When the user edits and saves the list, Then new mail follows it and the Telegram notice with Undo appears (AC-1, AC-2, AC-31) (type: happy)
  2. Given a rename, Then the Gmail label is renamed and no review is made (AC-40) (type: happy)
  3. Given all states of the page at the viewports, Then axe finds no violation (AC-23) (type: a11y)
  4. Given the canary strings, Then they are in no log, error or notice (AC-30) (type: security)
  5. Given the web lock, Then the page refuses and says how to unlock (AC-32) (type: security)
