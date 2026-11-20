---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-18: Review moves page

- Component: web
- Layer: web
- Release: R2
- Contract: `/review`: overview states, groups with disclosure, per-group Approve and 'Keep all in place', per-mail checkboxes, 'Select all N in this group', Load more, selection count in one debounced live region, approve summary dialog (tone safe) and Move back dialog (danger), build progress, cap, scheduled with Cancel, applied with skipped and failed, replaced, 403 lock.
- Files: apps/web/src/features/review/*, apps/web/src/api/plan/*, apps/web/src/router/*
- Depends on: U-mail-categories-08, U-mail-categories-17
- Parallel: no
- Guardrails: guardrail-typescript, guardrail-react, guardrail-vitest-rtl, guardrail-a11y, guardrail-tailwind, guardrail-react-router, guardrail-tanstack-query
- Criteria:
  1. Given a plan with groups, Then they are collapsed with count and per-group Approve and Keep all in place (AC-12) (type: happy)
  2. Given a group, When 'Select all 80 in this group' is pressed, Then it only selects; 'Approve group' records the decision (AC-13) (type: happy)
  3. Given selected mails, Then the button reads 'Move N mails, labels only' and the summary dialog names counts per group (AC-13, AC-55) (type: happy)
  4. Given a plan being built, Then it shows 'n of about m checked, nothing moves yet' and the number not looked at (AC-43) (type: happy)
  5. Given a list of 1 000 items, Then pages of 100 with Load more render within the bound and keep a stable DOM so focus stays on a ticked box (AC-24) (type: edge)
  6. Given sender names with bidi or look-alike characters, Then the real address shows beside the name and format characters are removed (AC-44) (type: security)
  7. Given scheduled, applied, replaced, skipped, failed, cancelled and 403 states, Then each shows its banner and copy (type: error)
  8. Given only the keyboard and a screen reader, Then disclosure, selection announcements (one live region) and the dialog work (AC-23) (type: a11y)
  9. Given 320, 375, 768 and 1280 px and 200 % text, Then no horizontal scroll and the sticky bar never covers the focused checkbox (AC-23) (type: a11y)
