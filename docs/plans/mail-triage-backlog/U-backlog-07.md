---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-07: CatchUp use case: flow, order, skip and finish

- Layer: backend (use case)
- Contract: `CatchUp(mailbox, judge, store, notifier, budget, now).run_once() -> RunSummary`. On the first call it stores the cut-off (`start_catchup(now)`); a finished catch-up returns at once. Each run lists the mails (U-04), takes at most `RUN_LIMIT = 20` unfinished mails in the listed order (newest first), fetches, claims (`DONE`: skip), judges, decides (U-05), files and calls `complete_backlog`. When every listed mail is done and no retry is pending it calls `finish_catchup`. Failures use `record_failure`, `MAX_ATTEMPTS` and `notify_failure` like the pipeline.
- Files: `app/usecases/catchup.py`, `tests/usecases/test_catchup.py`
- Depends on: U-02, U-03, U-04, U-05
- Parallel: no
- Guardrails: guardrail-gmail, guardrail-llm
- Criteria:
  1. Given no catch-up state, When it runs, Then the cut-off is stored before any mail is touched (type: happy; AC-B4).
  2. Given three unread mails, When it runs, Then each is filed with one label and the inbox label is removed, in the listed (newest first) order (type: happy; AC-B1, AC-B9).
  3. Given a mail already filed earlier, When it runs, Then it is skipped and not judged (type: edge; AC-B6).
  4. Given 25 unread mails, When it runs once, Then 20 are processed and the catch-up is not finished (type: edge).
  5. Given nothing is left, When it runs, Then the catch-up is finished and a second `run_once` does nothing and calls neither the mailbox nor the judge (type: happy; AC-B5).
  6. Given a finished catch-up, When the agent is rebuilt (new store, new use case), Then it still does nothing (type: edge; AC-B5).
  7. Given a mail that fails three times, When it runs repeatedly, Then it is abandoned with one notice and the next mail is processed (type: error; AC-B12).
  8. Given the model is down, When it runs, Then the run stops, nothing is filed wrongly and the catch-up is not finished (type: error).
  9. Given the mailbox port, When the catch-up runs, Then it only calls list, fetch, ensure-label and file, never a delete (type: security; AC-B3).
  10. Given any run, When logs are inspected, Then they hold counts and ids only (type: security; AC-B13).
