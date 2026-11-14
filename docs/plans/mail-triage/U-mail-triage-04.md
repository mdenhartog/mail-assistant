---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-04: Judgement schema and category policy

- Layer: backend (pure core)
- Contract: `Judgement` model (`category`, `urgent`, `reason`, `summary`, `confidence`) with strict validation; `resolve(judgement, existing_labels) -> Decision` (uses a label, creates a label, or needs-attention).
- Files: `app/core/judgement.py`, `tests/core/test_judgement.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-pydantic, guardrail-llm
- Criteria:
  1. Given valid model output, When parsed, Then a `Judgement` is returned (happy).
  2. Given extra fields, wrong types or a missing field, When parsed, Then it is rejected and the decision is needs-attention (error, security; AC-18).
  3. Given confidence below the threshold, When resolved, Then needs-attention (edge; AC-18).
  4. Given a category that exists, When resolved, Then that label is used (happy; AC-1).
  5. Given a new category name that matches `Assistant/<name>` and fewer than 15 exist, When resolved, Then it is created (happy; AC-13).
  6. Given 15 categories exist or the name breaks the pattern (path characters, over-long), When resolved, Then the closest existing category or `Assistant/Other` is used and no label is created (security; AC-13).
  7. Given `reason` or `summary` longer than the cap, When parsed, Then it is cut at the cap (edge; AC-21).
