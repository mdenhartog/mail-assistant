---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-02: Alert state machine

- Layer: backend (pure core)
- Contract: `transition(state, event) -> state` for states `held, open, snoozed, drafting, confirming, closed` and events `quiet_end, remind_later(due), close, start_draft, show_draft, cancel_draft, sent, due`; illegal transitions raise `InvalidTransition`.
- Files: `app/core/alert_state.py`, `tests/core/test_alert_state.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: —
- Criteria:
  1. Given an `open` alert, When `close` happens, Then it is `closed` and never returns to `open` (happy; AC-10).
  2. Given an `open` alert with no event, When time passes, Then it stays `open` and no new alert is requested (edge; AC-5).
  3. Given `open`, When `remind_later` with a due time, Then `snoozed`; When `due`, Then `open` again exactly once (happy; AC-9).
  4. Given `confirming`, When `cancel_draft`, Then `open` (happy; AC-8).
  5. Given `confirming`, When `sent`, Then `closed` (happy; AC-7).
  6. Given `closed`, When any event except a new mail arrives, Then `InvalidTransition` (error).
