---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-14: Plan build

- Component: mail-triage
- Layer: backend
- Release: R2
- Contract: `usecases/resort_build.py`: debounce, one build, scope (inbox or an `Assistant/` label; not spam, trash, Archive, pinned, rejected; two `Assistant/` labels counted unclear), newest first up to 5 000, judging within the budget above the reserve, items only when the category would change, progress cursor, first plan at the first start, 'plan ready' notice with numbers.
- Files: agents/mail-triage/app/usecases/resort_build.py, agents/mail-triage/app/core/scope.py, agents/mail-triage/tests/test_resort_build_*.py
- Depends on: U-mail-categories-05, U-mail-categories-12, U-mail-categories-13
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-llm, guardrail-gmail
- Criteria:
  1. Given the label-state matrix (inbox, label, Archive, spam, trash, two labels, legacy, deleted, draft), Then only mail in scope can become an item (AC-10, AC-52) (type: edge)
  2. Given a changed list, Then items exist only for mails whose category would change and nothing moves (AC-9) (type: happy)
  3. Given 5 001 mails in scope, Then the newest 5 000 are in the plan and the rest is reported as not looked at (AC-11) (type: edge)
  4. Given zero budget above the reserve, Then the reserve is never used, the plan stays `building` and continues after the day boundary (AC-11) (type: error)
  5. Given several saves in a short time, Then one build starts after the debounce and a newer list cancels it without half-written items (AC-33) (type: edge)
  6. Given R2's first start with no plan, Then a plan is built against the current list (AC-54) (type: happy)
  7. Given a deleted category, Then its mails are items and the label is not deleted (AC-17) (type: happy)
  8. Given rejected mail, Then it stays out until the list changes again (AC-13) (type: edge)
  9. Given the plan notice, Then it holds numbers only (AC-18) (type: security)
