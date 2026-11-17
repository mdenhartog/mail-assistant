---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-30: Categories page leave guard and save bar

- Component: web
- Layer: web
- Release: R1
- Contract: a notice where a removed card was; a leave question while changes are unsaved; a sticky save bar on small screens with a count of unsaved changes; a save summary that names each change; clearer not-ready, older-categories and limit texts with a Check again button; a session that ended or the web lock reaches sign-in past the leave question (AC-32).
- Files: apps/web/src/features/categories/**, apps/web/e2e/categories.spec.ts
- Depends on: U-mail-categories-09
- Parallel: no
- Guardrails: guardrail-react, guardrail-react-router, guardrail-typescript, guardrail-vitest-rtl, guardrail-a11y
- Criteria:
  1. Given unsaved edits, When the user leaves the page, Then a question asks first (type: happy)
  2. Given unsaved edits and a 401 or the lock, When the app navigates to sign-in, Then no question blocks it (type: security)
  3. Given changes, Then the save summary names each change (type: happy)
  4. Given a small screen, Then the save bar stays visible and counts the changes (type: a11y)
  5. Given the list is not ready, Then the text says why and a Check again button retries (type: error)
