---
intent: INT-008
feature: label-structure
---

# U-label-structure-38: Web: the skipped count beside a sender entry (R1)

- Component: web
- Layer: web
- Contract: the Senders field of the edit view shows, for every listed entry whose `skippedCount` is above 0, a line "Not applied 3 times: Gmail could not confirm the sender" (a count and a fixed text, never mail content), and a short note under the field that the AI judged those mails. The count is plain text in the field's description (not a control), so keyboard and screen-reader users get it, and a round trip through the form does not send it back (the web client strips it from the `PUT` body).
- Files: `apps/web/src/features/categories/SendersField.tsx`, `apps/web/src/features/categories/copy.ts`, `apps/web/src/features/categories/rows.ts`, tests (unit and the a11y e2e of unit 17)
- Depends on: U-label-structure-15, U-label-structure-37
- Parallel: no
- Guardrails: guardrail-react, guardrail-typescript, guardrail-vitest-rtl, guardrail-a11y
- Criteria:
  1. Given an entry with a count of 3, When the edit view opens, Then the line shows 3 times and the screen reader reads it with the field. (type: happy)
  2. Given every count 0, When the edit view opens, Then no skip line shows. (type: edge)
  3. Given a save, When the body is built, Then no `skippedCount` is sent. (type: security)
  4. Given 200 % text at 320 px, When the line shows, Then nothing is clipped or overlaps. (type: a11y)
