---
intent: INT-008
feature: label-structure
---

# U-label-structure-16: Web: upload, preview, restore and export (R1)

- Component: web
- Layer: web
- Contract: the upload controls (native file input and a keyboard-operable drop zone), the preview (counts in bold, removed categories in their own block with the sentence, words and an icon for added, changed and removed), the confirm button "Replace my whole list (N removed)" (not the default focus when anything is removed), errors with line and field and a copy option, "Restore previous version", export with a copy option, links to the template and example.
- Files: `apps/web/src/pages/categories/upload/`, `apps/web/src/api/categories/upload.queries.ts`, tests
- Depends on: U-label-structure-12, U-label-structure-13, U-label-structure-15
- Parallel: no
- Guardrails: guardrail-react, guardrail-typescript, guardrail-tanstack-query, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given a valid file, When uploaded, Then the preview shows "3 added, 5 changed, 2 removed" and the removed block with its sentence. (type: happy)
  2. Given removals, When the preview shows, Then the confirm button reads "Replace my whole list (2 removed)" and is not the default focus. (type: a11y)
  3. Given an invalid file, When uploaded, Then errors show line and field and can be copied; nothing changes. (type: error)
  4. Given a confirmed upload, When it finishes, Then "Restore previous version" is offered and works. (type: happy)
  5. Given the export, When used, Then it downloads `mail-categories.yaml` and offers a copy option; the template and example are linked. (type: happy)
  6. Given added, changed and removed, When shown, Then each is marked with words and an icon, not colour alone. (type: a11y)
  7. Given a 409 on confirm, When it comes back, Then the page says the list changed and asks to upload again. (type: error)
