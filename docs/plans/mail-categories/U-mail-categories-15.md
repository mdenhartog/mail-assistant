---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-15: Plan apply and Move back

- Component: mail-triage
- Layer: backend
- Release: R2
- Contract: `usecases/resort_apply.py`: takes `scheduled` plans past `apply_after`, per mail re-checks scope, old label, pinning and the proposed category, moves via `gmail_resort`, writes `apply_audit`, removes items, result notice; Move back from `move_back_request` and `apply_audit`; lock check before every batch.
- Files: agents/mail-triage/app/usecases/resort_apply.py, agents/mail-triage/app/usecases/move_back.py, agents/mail-triage/tests/test_resort_apply_*.py
- Depends on: U-mail-categories-06, U-mail-categories-14
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given approved items, When applied, Then the old label is removed and the new added, nothing is deleted or sent (AC-14) (type: happy)
  2. Given a mail moved, deleted or archived meanwhile, or gaining `Archive`, Then the item is skipped with a reason (AC-15, AC-35) (type: edge)
  3. Given a proposed category no longer in the list, Then the item is skipped (AC-26) (type: edge)
  4. Given two apply runs at once, Then each mail moves once (AC-35) (type: security)
  5. Given a Gmail success followed by a database failure, When repeated, Then the item ends applied and nothing moves twice (AC-51) (type: error)
  6. Given Lock during `applying`, Then it stops before the next batch (AC-57) (type: security)
  7. Given pinned mail, Then it is never moved (AC-39) (type: security)
  8. Given Move back, Then old labels are restored from `apply_audit`, skipping changed mail, once per plan, with one notice (AC-41, AC-57) (type: happy)
  9. Given an apply, Then the result notice has counts, Move back and Lock and names empty labels (AC-18, D18) (type: happy)
