---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
design: docs/design/web-settings-design.md
status: approved
approver: Marco
date: 2026-11-10
---

# Web settings: prototype brief

Route B of ADR-0009: the prototype was built here and published as a private artifact for Marco; the source is `docs/design/web-settings-prototype.html`. Direction: Pebble (ADR-0035).

## What the prototype had to answer

1. Does the settings form read well and work on a phone abroad: zone first, the three times as clock times in that zone, one card per setting?
2. Is finding a time zone by city, country or UTC offset quick, and does the live local time help?
3. Is it clear what a zone change does to quiet hours before saving (the preview line)?
4. Does a conflict (409) keep Marco's own values visible next to the new ones without losing anything?

## Scope

In: the settings page with its four fields, the zone combobox, the zone-change preview, validation next to the field, the saving and saved states, the conflict banner with "Use mine" and "Keep Telegram's", and the other states and the login page as prototype buttons. Out (R2): Reset to defaults (shown disabled), typed values kept across session expiry beyond the memory draft, the refused-sign-in alert.

## Flows to try (as given to Marco)

1. Time zone: type `Bang`, `Portugal` or `UTC+7`; type `Phuket` for the "nothing found" hint.
2. Validation: set the daily overview to 23:00 and press Save.
3. Conflict: change From, press "Simulate a Telegram change", press Save.
4. States: loading, save failed, session expired, sign-in refused and sign-in error.

## Comments

Marco approved the direction without changes on 2026-11-10 ("this is the direction"). No comment is open.
