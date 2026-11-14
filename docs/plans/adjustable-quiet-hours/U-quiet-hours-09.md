---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-09: Settings dialogue: card, times, quiet hours, conflicts

- Layer: backend
- Contract: `SettingsDialog` handles `/settings`, the card, the time questions for the overview and the reminder default, the two-step quiet hours, refusal texts with rule and example, and the one-tap move of a conflicting value.
- Files: `app/usecases/settings_dialog.py`, `app/core/settings_text.py`, `tests/usecases/test_settings_dialog.py`
- Depends on: U-quiet-hours-01, U-quiet-hours-05, U-quiet-hours-07
- Parallel: yes (with U-06b)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given the allowed user, When `/settings` is sent, Then four labelled values with a "Change" button each (AC-2) (type: happy).
  2. Given the quiet-hours question, When a valid start and end come, Then both are stored together (AC-13) (type: happy).
  3. Given a valid start and then Cancel, an invalid end, or a database fault between the steps, When it happens, Then neither value is stored (AC-13) (type: error).
  4. Given the 22:00-11:00 answer, When refused, Then the message names the rule, the value and "Try 22:00 to 10:00" (type: error).
  5. Given overview 18:00 and a new window 17:00-03:00, When saved, Then refused and a one-tap move of the overview is offered; taking it stores both (AC-11) (type: edge).
  6. Given the time forms and refused texts of U-01, When answered in the dialogue, Then stored or refused as there, and nothing reaches a query (AC-8, AC-9) (type: security).
  7. Given a `VersionConflict`, When saving, Then the bot says it changed elsewhere and shows the card again (AC-29) (type: edge).
  8. Given each question, Then it names the value and the step and has a Cancel button (type: a11y).
  9. Given a failure path, When logs are captured, Then no token or zone value appears (AC-33) (type: security).
