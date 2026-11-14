---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-03: Budget remaining

- Layer: backend
- Contract: `DailyBudget.remaining() -> int`, read-only (never spends), resets with the date like `try_spend`.
- Files: `app/adapters/judge_anthropic.py`, `tests/adapters/test_judge_anthropic.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-llm
- Criteria:
  1. Given a budget of 5 and 2 calls spent, When `remaining()` is read, Then it is 3 and a second read is still 3 (type: happy).
  2. Given all calls are spent, When `remaining()` is read, Then it is 0 (type: edge).
  3. Given the date changes, When `remaining()` is read, Then it is the full limit again (type: edge).
