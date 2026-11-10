---
feature: web-settings
intent: INT-002
brief: docs/design/web-settings-brief.md
prototype: docs/design/web-settings-prototype.html
status: approved
approver: Marco
date: 2026-11-10
---

# Web settings: hand-off from the prototype to the build

The approved look and behaviour of the settings page. The authority for words, states and components stays `web-settings-screens.md`; where the prototype and that document differ, the differences are listed here.

## What was checked in a real browser (Chromium, 2026-11-10)

- The zone combobox, the zone-change preview, validation, saving, the saved banner, the conflict banner and "Use mine" followed by a successful save all work as described.
- At 320, 375, 768 and 1280 px, and at 200 % text size, there is no horizontal scroll and every control is at least 44 px.
- Every visible text pair passes WCAG 2.2 AA in light and in dark. A defect found on the way (the check and exclamation marks in the banners had the colour of their own background) is fixed in the saved file.
- Not checked: a screen reader, a real touch device, 12-hour time display of `type="time"`, browsers other than Chromium. The build tests cover them with Vitest and axe and Playwright (units of the plan).

## Tokens

The source of the tokens is the `:root` and `:root[data-theme=dark]` blocks at the top of the prototype. The tokens unit converts them to `packages/tokens/tokens.json` with `design-tokens-bridge`, replacing the placeholder tokens:

- Colours, each with a light and a dark value: `surface`, `surface-raised`, `text`, `text-muted`, `border`, `divider`, `primary`, `primary-contrast`, `danger`, `danger-soft`, `success`, `success-soft`, `focus` (the nine existing names are kept; `border`, `divider`, `danger-soft` and `success-soft` are new).
- Fonts: Bricolage Grotesque for headings, Figtree for text, each with a system fallback stack.
- Radius: 999 px (buttons), 14 px (controls), 24 px (cards and the greeting bubble). A soft shadow. Space steps from 0.25 to 2 rem. Type steps from 0.875 to 2 rem. Motion: 200 ms press, 250 ms enter, a spring curve for presses; all removed under `prefers-reduced-motion`.
- The contrast test of `packages/tokens` must cover text at 4.5:1 and borders, focus rings and controls at 3:1.
- Banner icons use a separate foreground variable for the circle (`--bf`), not `currentColor`.

## Behaviour to carry over

- Field order: Time zone, Quiet hours (From, a visible "until", Until, each with a 24-hour echo "= 22:00"), Daily overview, Remind-me-later default; a permanent sentence that the times follow the time zone.
- Zone combobox as in the prototype: options read "Bangkok, Thailand, UTC+7, 03:42 now" with "(tomorrow)" or "(yesterday)" when the day differs, computed in the browser from `utcOffsetMinutes` and the zone; `UTC+7` and `GMT+7` are accepted; "nothing found" is a hint; a second Escape restores the saved value; never empty on blur; "Currently: ..." line.
- Zone-change preview line while the form is dirty.
- Saving state keeps focus on Save (`aria-disabled`), inputs read-only, polite status "Saving your settings."
- Saved banner with the real notice interval instead of the fixed "about 5 minutes"; last-change line.
- Conflict: banner with focus, unedited fields take the new values, edited fields keep Marco's value and show both values with "Use mine" and "Keep Telegram's" as toggle buttons with text "Using ...", nothing saved until Save is pressed again.

## Differences from the screens document and the production design

| Prototype | Production |
| --- | --- |
| A hand-made list of 34 places with aliases | The real lookup of ADR-0028 through `/api/places`; the option text is built from `label` and `utcOffsetMinutes` |
| Validation messages for empty times and for From equal to Until written in the prototype | Messages come from the shared validation package (`Problem` rule, value and example) mapped to the field; for the same rules the wording is that of Telegram |
| "Nothing is saved until you press Save again." in the conflict banner | Kept; already added to `web-settings-screens.md` |
| "Not in this version." beside a disabled Reset button | The button is not rendered in R1; it arrives in R2 |
| The draft lives in memory only | R1 has no draft across a session expiry; R2 stores it (see the spec) |
| No fallback for browsers without `type="time"` | A stepped select with a stored value that is not on the grid shown as is, as in `web-settings-screens.md` |

## Prototype only (not built)

The "Prototype: simulate a change made in Telegram" box and its read-out of the stored copy, the "Prototype: states" buttons, the "How to try this prototype" list, the fake server delay (0.7 s loading, 0.9 s saving) and the theme button (production follows the system setting and the tokens).
