---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-09: CatchUp use case: alert cap

- Layer: backend (use case)
- Contract: an urgent old mail gets its alert (state from the shared `decide_outcome`, so quiet hours still apply) only while `store.backlog_alerts() < BACKLOG_ALERT_LIMIT` (5). At the limit the outcome is stored with `alert=None` (still `urgent = true`), so the overview lists it (U-06).
- Files: `app/usecases/catchup.py`, `tests/usecases/test_catchup.py`
- Depends on: U-08
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given seven urgent old mails, When the catch-up runs, Then exactly five alerts exist, for the five newest (type: happy; AC-B10).
  2. Given the two other urgent mails, When they are filed, Then they are filed urgent without an alert (type: happy; AC-B10).
  3. Given five alerts from an earlier run and a restart, When another urgent old mail is judged, Then no sixth alert is created (type: edge; AC-B10, T-24).
  4. Given an urgent old mail inside quiet hours, When it gets an alert, Then it is held until the quiet hours end (type: edge; AC-B11).
  5. Given an injected mail that the model calls urgent, When the cap is reached, Then no extra alert follows (type: security; AC-B14).
