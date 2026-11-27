---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-06: The series rules (pure)

- Component: mail-triage agent
- Layer: backend
- Contract: A pure `core/resort_series.py` with `SeriesState`, `PauseReason` (the fixed set of U-03) and `decide(series, now_day, events) -> Decision`: `start_next_part`, `wait(reason)` or `end(reason)`. A series ends on Cancel, Undo, Lock of any part, a web lock, a list change, the cap of 5 000 mails, a part open for 14 days (`expired`) or a series age of 14 days. The next part starts only on a later UTC day and only when the previous part has no non-terminal plan. The system never approves a part of an ended series. No clock and no I/O.
- Files: `agents/mail-triage/app/core/resort_series.py`, tests under `agents/mail-triage/tests/core/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given part 1 is finished and the next UTC day starts, When decided, Then `start_next_part` (AC 4). (type: happy)
  2. Given part 1 is ready, scheduled or applying, When the next day starts, Then `wait(waiting_for_part)` (AC 5). (type: edge)
  3. Given Cancel, Undo or Lock on any part or a web lock, When decided, Then `end(ended)` and never `start_next_part` (SAC-13, AC 15). (type: security)
  4. Given a list change, When decided, Then `end(ended)` (AC 6). (type: edge)
  5. Given 5 000 mails checked over several parts, When decided, Then `end(ended)` and the rest is "not looked at" (AC 7). (type: edge)
  6. Given a part open for 14 days, When decided, Then `end(expired)` (SAC-12, AC 16). (type: security)
  7. Given a series older than 14 days, When decided, Then `end(expired)` (AR-C). (type: security)
  8. Given an ended series (property test), When any event arrives, Then the decision is never `start_next_part`. (type: security)
  9. Given a part with one mail checked, no moves and all items unclear, When decided, Then its plans are terminal, the mails count toward the cap and the next part may start (spec D2). (type: edge)

Time enters as arguments (the database day, hour and ages), never from a clock. Mutation testing runs on this unit; coverage of the changed code is at least 90 %.
