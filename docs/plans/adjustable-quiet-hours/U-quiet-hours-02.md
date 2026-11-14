---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-02: Place list and lookup

- Layer: backend (shared package)
- Contract: `places.lookup(text) -> LookupResult` (hits with label and UTC offset, near-miss suggestion, or nothing); countries with several zones return city-named zones; a typed IANA name is accepted if listed (ADR-0028).
- Files: `schedule_policy/places.py`, `schedule_policy/places.json`, `packages/schedule-policy/tests/test_places.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python
- Criteria:
  1. Given "New York" in any case or accent, When looked up, Then America/New_York (AC-14) (type: happy).
  2. Given "Paris", "Sydney", "Georgia", When looked up, Then at most 5 labelled hits (AC-15) (type: edge).
  3. Given "Nwe York", When looked up, Then the suggestion "New York" (AC-16) (type: error).
  4. Given text matching nothing, When looked up, Then an empty result (AC-17) (type: error).
  5. Given "USA" and "Australia", When looked up, Then zones with city names (AC-18) (type: happy).
  6. Given "Europe/Paris", When looked up, Then accepted; Given an unlisted IANA name, Then nothing (AC-19) (type: edge).
  7. Given aliases "NYC", "Wien", "Den Haag", surrounding spaces and "Zürich", When looked up, Then matched (type: edge).
  8. Given the list, When checked against `tzdata`, Then every zone exists and every entry has a label (type: security).
  9. Given a 64-character and a 65-character text, When looked up, Then the second is refused before matching (AC-9) (type: security).
  10. Given NFC and NFD "Zürich", a Turkish dotless i, full-width Latin letters and "São Paulo", When looked up, Then each matches (type: edge).
  11. Given "Georgia", When looked up, Then both the country and the US state hits are offered (type: edge).
