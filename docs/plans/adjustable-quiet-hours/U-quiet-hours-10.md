---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-10: Zone dialogue

- Layer: backend
- Contract: the time-zone question in `SettingsDialog`: lookup per U-02, buttons for several hits and for large countries, the near-miss suggestion, the nothing-found message with a hint and Cancel, storing the chosen zone.
- Files: `app/usecases/settings_dialog.py`, `app/core/settings_text.py`, `tests/usecases/test_zone_dialog.py`
- Depends on: U-quiet-hours-02, U-quiet-hours-09
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given "New York", When answered, Then America/New_York is stored (AC-14) (type: happy).
  2. Given "Paris", When answered, Then at most 5 buttons "Paris, France (UTC+1)"; the chosen one is stored (AC-15) (type: edge).
  3. Given "Nwe York", When answered, Then "Did you mean New York?" with buttons (AC-16) (type: error).
  4. Given nothing found, When answered, Then the bot says so, suggests the nearest big city or the country, shows Cancel, stores nothing (AC-17) (type: error).
  5. Given "USA", When answered, Then zone buttons with city names (AC-18) (type: happy).
  6. Given `../etc` or SQL text, When answered, Then nothing is stored and the zone lookup is not called with it (AC-9) (type: security).
  7. Given a button for an index outside the stored candidates, When tapped, Then nothing changes (type: security).
  8. Given `Europe/Paris` typed, Then stored; Given an unlisted IANA name such as `Pacific/Kiritimati`, Then nothing found and the name never appears in logs (AC-19, AC-33) (type: security).
