---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-42: The web page and the guide speak of the archive label, not of Archive

- Component: agents/mail-triage
- Layer: backend
- Release: R2
- Contract: the Categories page says that mail in the user's archive label in Gmail is never re-sorted, without naming the label; the user guide names the default `Assistant/Archive` and the setting `ARCHIVE_LABEL`.
- Files: apps/web/src/features/categories/Intro.tsx, apps/web/src/features/categories/CategoriesPage.test.tsx, docs/user-guide/mail-categories.md, deploy
- Depends on: U-mail-categories-41
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given the Categories page, Then the note says the archive label is left alone and names no label (type: happy)
  2. Given the chart and the compose file, Then they carry `ARCHIVE_LABEL` with the default (type: ops)
