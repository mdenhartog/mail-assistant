---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-05: Share the decision step (refactor, no behaviour change)

- Layer: backend
- Contract: `decide_outcome(verdict, mail, known_labels, now) -> Outcome` becomes a module-level function in `app/usecases/triage.py`; `TriagePipeline` calls it. No new parameter, no flag. This is a pure refactor: the existing tests stay green and are not edited.
- Files: `app/usecases/triage.py`, `tests/usecases/test_triage.py` (one added test)
- Depends on: —
- Parallel: yes
- Guardrails: —
- Criteria:
  1. Given a judgement, When `decide_outcome` is called directly, Then it returns the same outcome as the pipeline produced before (type: happy).
  2. Given a `NeedsAttention` verdict, When `decide_outcome` is called, Then the label is `Assistant/Other`, urgent, with the same note as before (type: edge).
  3. Given the full existing test suite of the pipeline, When it runs, Then every test passes unchanged (type: regression).
