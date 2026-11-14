---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-11: Confirmation and Undo

- Layer: backend
- Contract: after a successful write the bot sends the full picture (zone with UTC offset, local time there and in the previous zone, quiet hours in both, next overview, next clock change within 14 days) and an Undo button; Undo calls `SettingsStore.undo`.
- Files: `app/usecases/settings_confirm.py`, `app/core/settings_text.py`, `tests/usecases/test_settings_confirm.py`
- Depends on: U-quiet-hours-10
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given a zone change to America/New_York at a fixed UTC moment (`FakeClock`), When confirmed, Then the text has the offset, 17:05 there and 23:05 Amsterdam, the quiet hours in both, the next overview (AC-20) (type: happy).
  2. Given a clock change within 14 days, When confirmed, Then the date is mentioned; Given none, Then not (type: edge).
  3. Given Undo with an unchanged row, When tapped, Then the previous values return and a new confirmation is sent (AC-21) (type: happy).
  4. Given Undo after another change, When tapped, Then nothing changes and the bot says so (AC-21) (type: edge).
  5. Given a confirmation of a non-zone change, Then the quiet hours and times are shown without a zone comparison (type: edge).
  6. Given Asia/Kolkata, When confirmed, Then the offset is labelled "UTC+5:30" (type: edge).
  7. Given Undo tapped after 15 minutes or after a restart, When handled, Then it works if the row is unchanged, otherwise the bot says so (AC-21) (type: edge).
