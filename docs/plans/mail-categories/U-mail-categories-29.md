---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-29: Review page wording and status

- Component: web
- Layer: web
- Release: R2
- Contract: a status text for loading; a button that says what it does and that only labels change; a reworded approval dialog and scheduled notice; when the mails moved, with plain reasons for those that did not; a status chip per group so the user can look before approving.
- Files: apps/web/src/features/review/**, apps/web/e2e/review.spec.ts
- Depends on: U-mail-categories-18
- Parallel: no
- Guardrails: guardrail-react, guardrail-typescript, guardrail-vitest-rtl, guardrail-a11y, guardrail-tailwind
- Criteria:
  1. Given the review page is loading, Then the loading text is announced as a status (type: a11y)
  2. Given a plan is ready, Then the button says how many mails move and that only labels change (type: happy)
  3. Given the approval dialog, Then it names what happens and how to stop it (type: happy)
  4. Given moved and unmoved mails, Then the page shows when they moved and a plain reason for each unmoved one (type: happy)
  5. Given a group, Then it carries a status chip and can be looked at before approving (type: happy)
