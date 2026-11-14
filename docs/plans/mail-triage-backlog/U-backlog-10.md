---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-10: Run the catch-up in the mail cycle

- Layer: backend (wiring)
- Contract: `Runner` gets a `CatchUpPort` and one `_guard("catchup", ...)` step after `pipeline`; `wiring.build` constructs `CatchUp` with the existing mailbox, judge, store and the same `DailyBudget` instance. A failing catch-up never stops the other steps.
- Files: `app/runner.py`, `app/wiring.py`, `tests/test_runner.py`, `tests/test_wiring.py`
- Depends on: U-07, U-08, U-09
- Parallel: no
- Guardrails: —
- Criteria:
  1. Given a mail cycle, When it runs, Then the order is release, pipeline, catch-up, deliver, overview, purge (type: happy; AC-B7).
  2. Given the catch-up raises, When the cycle runs, Then the later steps still run and the heartbeat is touched (type: error).
  3. Given the wiring, When the judge and the catch-up are built, Then they share one `DailyBudget` (type: edge; AC-B15).
  4. Given an installation with a stored history position and no catch-up state, When the agent starts, Then the catch-up starts without any setting or command (type: happy; AC-B4).
