---
feature: mail-categories
intent: INT-004
brief: docs/design/mail-categories-brief.md
prototype: docs/design/mail-categories-prototype.html
artifact: https://claude.ai/artifact/531djHF6wdbNaAsVcuCjqm (version 2)
status: approved
approver: the user
date: 2026-11-14
---

# Mail categories: hand-off from the prototype to the build

The user approved version 2 of the prototype on 2026-11-14 ("now it is good"). Version 1 was rejected because its style did not match the built app (own bubble-less header, an invented warning colour, different banner, button, field and dialog looks). Version 2 copies the built components of `apps/web/src/components` and uses only the tokens of `packages/tokens/tokens.css`.

## Rule for the build

The built components are the authority for look and behaviour: `Layout`, `Button`, `Banner`, `Field`, `FieldGroup`, `ConfirmDialog` and the card grid of `SettingsFields`. The prototype shows how they are combined; its markup is not copied (clickable-prototype rule).

## Reuse and new components

| Need | Component |
| --- | --- |
| Page frame, header with "Signed in as", Sign out | existing `Layout` (gets a navigation, see below) |
| Buttons | existing `Button` (primary, secondary, ghost, danger) |
| Messages | existing `Banner` (danger, conflict, success, info); no warning colour exists, a "warn" state uses `conflict` or `info` |
| Name and description fields, errors | existing `Field` (label, hint above the control, error with the circle mark) |
| Confirmations (save summary, approve summary, move back) | existing `ConfirmDialog` (safe button first and focused, confirm danger) |
| Category card | a `Card` taken from `SettingsFields` into `src/components` (`rounded-card bg-surface-raised p-5 shadow-soft`) |
| Loading | the grey pulsing blocks of `SettingsPage` |
| Main navigation with an open-items badge | new `MainNav` in `src/components`, tokens only |
| Group with a disclosure header, count, "Approve group", "Keep all" | new `ReviewGroup` in `src/features/review` |
| Mail row with checkbox, sender name and address, subject | new `ReviewItem` |
| Progress bar | new `Progress` |
| Sticky action bar with the effect-naming button | new `ActionBar` |

New values need a token first; the prototype needed none.

## Changes decided in the phase 3 round table (apply when building; the prototype is not republished)

- `ConfirmDialog` gets a `tone` (safe or danger): saves and label-only moves use a normal confirm button, "replaces the review" and "Move back" stay red; cancel first in the DOM, focus trap over every focusable element, Escape cancels (AC-55).
- One debounced polite live region for the selection count; group rows keep a stable DOM; "Select all N in this group" only selects; "Keep all in place".
- Group header over two rows on narrow screens, 44 px targets, `scroll-padding-bottom` so the sticky bar never covers the focused checkbox; navigation is a `nav` with links and `aria-current`, badge text "842 open items"; `Progress` has `role=progressbar` with value text.
- Extra states: too many saves ("Too many saves. Wait a minute and try again."), applying, cancelled, review group loading and empty; "No review is open" links to "Edit your categories"; an honest expired-session text about where unsaved edits are kept; an inline undo after deleting a category.
- R1 page text: "Old mail stays where it is for now." (no review in R1); "Older category" with "Add to my list" is in R1.

## Screens and flow

As in `mail-categories-brief.md`: Categories (all states of the brief), a save summary dialog, Review moves (no plan, building, ready, cap reached, scheduled, applied with skipped and failed and "Move back", replaced, lock), group expand with paging and select-all, approve summary dialog (a plan above 50 mails is scheduled with Cancel). The state switches at the top of the prototype are not part of the product.

## Deviations from the brief

- "Save changes" is the inline button at the end of the form, as on the Settings page, not a sticky bar. The sticky bar is only used on Review moves.
- The save summary and the approve summary are `ConfirmDialog`s, so the confirm button is the danger style; the safe button is first and has the focus.
- "Archive" hint and the "never re-sorted" text are an info banner on the Categories page.
- Fonts: the prototype loads Google Fonts; the app uses the self-hosted fonts of the tokens package (ADR-0035).

## Not checked

A screen reader, a real touch device and browsers other than the artifact viewer; the build tests (Vitest, axe, Playwright at 390, 820, 1440 px and 200 % zoom) cover them. The prototype was checked for script syntax only, not clicked through by me.

## Comments

None open. The user approved the direction after one correction (the style), which is applied in version 2.
