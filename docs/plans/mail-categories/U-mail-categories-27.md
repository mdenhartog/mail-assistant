---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-27: Review fixes: archive label, names, authentication results, log redaction

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: RED-003 (the archive label is matched case-insensitively in one shared helper), RED-004 (dot-dot is refused in names and a refused label files under Other), RED-005 (Authentication-Results is parsed as RFC 8601 and fails closed when ambiguous), SEC-03 (mail headers are redacted from logs and error reports whatever their case), SEC-06 (line and paragraph separators show as a space on the review page).
- Files: agents/mail-triage/app/**, packages/category-policy/**, apps/web/src/features/categories/**, docs/memory/decisions/ADR-0048-pinned-mail-alerts.md
- Depends on: U-mail-categories-05, U-mail-categories-06
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail, guardrail-typescript
- Criteria:
  1. Given an `archive` label in any case, When labels are matched, Then one shared helper treats it as the Archive label (type: edge)
  2. Given a name containing `..`, When it is checked, Then it is refused (type: security)
  3. Given an ambiguous Authentication-Results header, When the sender is judged, Then it fails closed (type: security)
  4. Given a mail header in any case, When an error is reported or logged, Then its value is redacted (type: security)
  5. Given a line or paragraph separator in a name, When the review page shows it, Then it shows as a space (type: edge)
