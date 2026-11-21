---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-42: The web page and the guide speak of the archive label, not of Archive

- Component: apps/web, agents/mail-triage
- Layer: web
- Release: R2
- Contract: the Categories page says that mail in the user's archive label in Gmail is never re-sorted, without naming the label; the compose file passes the setting and the Helm worker takes it through its generic `env`; the user guide names the default `Assistant/Archive` and the setting `ARCHIVE_LABEL`.
- Files: apps/web/src/features/categories/Intro.tsx, apps/web/src/features/categories/CategoriesPage.test.tsx, docs/user-guide/mail-categories.md, agents/mail-triage/compose.yaml
- Depends on: U-mail-categories-41
- Parallel: no
- Guardrails: guardrail-react, guardrail-typescript, guardrail-vitest-rtl, guardrail-compose, guardrail-a11y
- Criteria:
  1. Given the Categories page, Then the note says the archive label is left alone and names no label (type: happy)
  2. Given the compose file, Then it carries `ARCHIVE_LABEL` with the default; the worker chart accepts `env.ARCHIVE_LABEL` (type: ops)
