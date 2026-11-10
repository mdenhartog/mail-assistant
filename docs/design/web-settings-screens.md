---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
status: approved
approver: Marco
date: 2026-11-10
---

# Web settings: screens, states and components

Direction: Pebble (ADR-0035): one soft card per setting (2 by 2 on desktop, stacked on a phone), pill buttons, one short greeting bubble at the top of the settings page that carries no control. Words per C-11 and AC-24. Mobile first; checked at 320, 375, 768, 1280 px and 200 % text size, no horizontal scroll (AC-22).

## Screen 1: Login page (`/login`, public)

Content: brand, heading "Sign in", the account to use ("Use the Google account `marco@example.com`. It is the only account that can open this app."), one provider button (label from configuration, "Continue with Google"), a fine-print line: "This page only asks who you are (your name and e-mail). It never asks for access to your mail or calendar."

| State | Behaviour |
| --- | --- |
| Default | Button focused order: the only interactive element; `h1` first in `main`. |
| Redirecting | Button disabled, text "Opening Google...", `aria-busy` on the button, status announced via a polite live region. |
| Refused (403 from callback) | Banner `role=alert`: "This account is not allowed for this app. Try the account named above." No error code, no detail from the provider. Focus moves to the banner heading or the button (the banner is rendered with the page on load, so it is announced). |
| Provider or network error | Banner: "Sign-in did not work. Try again. If it keeps happening, check your connection and the clock on your phone." with the same button. |
| Session expired (came from a save) | Info banner (`role=status`): "Your session ended. Sign in again; what you typed is kept." After sign-in return to `/settings` with the draft restored (AC-12). |
| Already signed in | Redirect to `/settings`. |

## Screen 2: Settings page (`/settings`, session needed)

Layout order: header (brand, Sign out as POST button), `h1` Settings, a quiet line "Signed in as `marco@example.com`" (also on phones), four fields in this order: **Time zone first**, then Quiet hours, Daily overview, Remind-me-later default; banner area, last-change line, actions. Save changes is primary; in R2 Reset to defaults is a separate secondary button kept apart from Save. At 320 px and at 200 % text the two buttons stack, Save first.

The time zone comes first because the three times are clock times in that zone. Under the times a permanent sentence says "Quiet hours, the overview and reminders follow this time zone." The Time zone hint reads "The times below are local times in this zone." After the zone is changed and before saving, a preview line shows what changes, for example "Quiet hours will now be 22:00 to 07:00 Bangkok time (16:00 to 01:00 Amsterdam time)." The clock times stay as they are; only the moment they mean moves.

Fields (words as Telegram): Quiet hours (From, Until), Daily overview, Remind-me-later default, Time zone. Each has a one-line hint linked by `aria-describedby`.

| State | Behaviour |
| --- | --- |
| Loading | Skeleton rows plus visible text "Loading your settings"; container `aria-busy=true`; skeleton animation removed under reduced motion. Save and Reset not rendered yet. |
| Loaded (clean) | Four values, last-change line "Last changed from Telegram at 14:02" (times via `Intl.DateTimeFormat`, in the saved zone; `<time datetime>`). Save disabled until something changed (optional; if enabled always, still validates). |
| Dirty | Save enabled. Leaving the page with unsaved edits asks the browser prompt only if cheap; draft kept in memory and in `sessionStorage` for the session-expiry return (no secrets). |
| Saving | Save and Reset disabled (`aria-disabled`), label "Saving..."; inputs `readonly`; status "Saving your settings." in a polite live region (AC-23). |
| Saved | Success banner (`role=status`) with what is true now: "Saved at 21:42. Quiet hours are 23:00 to 07:00 (Bangkok time). A message with an Undo button follows on Telegram within about N minutes." N is the agent's real run interval from its configuration. The last-change line becomes "Last changed from the web at 21:42". Focus stays on Save. If the audit trigger rolls the write back, the page says "Nothing was saved". |
| Validation error (AC-10) | Server or shared-validation message next to the field, text plus "!" mark plus red border (never colour alone), `aria-invalid=true`, `aria-describedby` hint + error, error element `role=alert`. On submit, focus moves to the first invalid field. Text matches Telegram, for example "The overview at 23:00 would fall inside quiet hours (22:00 to 07:00). Pick a time outside them, for example 18:00." Nothing stored. |
| Save failed (network or 5xx) | Danger banner `role=alert`: "Could not save. Nothing was changed. Check your connection and try again." with "Try again". Typed values stay. |
| Conflict (409, AC-11) | Info banner `role=alert`: "Settings changed in Telegram at 14:02 (Amsterdam time). I loaded the new values." The fields show the new values. Every field Marco had edited is marked with his own value and two buttons: "Use mine" and "Keep Telegram's" (for example "You typed 22:30, Telegram now has 23:00"). Nothing is lost silently and nothing is saved until he presses Save again. The last-change line updates. Focus moves to the banner. |
| Session expired (401 on save, AC-12) | R1: nothing is stored, Marco is sent to sign in and returns to `/settings` with the stored values. R2: the typed values are kept in memory and restored after sign-in, with the banner "Welcome back. Your unsaved changes are restored. Check them and save."; they are never saved automatically. |
| Access refused (403) | Full-page message: "This account is not allowed for this app." with "Back to sign in". No settings data in the DOM. |
| Reset to defaults (R2, AC-25) | Opens ConfirmDialog that names the values: "This replaces your saved settings with: Time zone Europe/Amsterdam, quiet hours 23:00 to 07:00, daily overview 18:00, reminders 09:00. It takes effect at once for new alerts." The destructive button says "Replace my settings with defaults"; initial focus is "Keep my settings". The dialog says that the time zone is reset too. On confirm: validated write, saving state, banner "Defaults restored. The Undo button is in the Telegram message." |
| Empty | Not applicable: a missing row means defaults (adjustable-quiet-hours), so the page always shows values. |

## Components (presentation layer, tokens only)

| Component | Anatomy and props | Keyboard | Screen reader |
| --- | --- | --- | --- |
| Button | variants primary, secondary, ghost, danger; `loading`, `disabled`; min 44 px high and wide | Tab, Enter, Space; `:focus-visible` ring from `focus` token, 3 px, 2 px offset | Native `button`; disabled-while-saving also sets `aria-disabled`; loading text changes ("Saving...") |
| Field | wrapper: label (or fieldset+legend for groups), hint, control slot, error slot; ids via `useId` | none of its own | Label linked with `htmlFor`; hint and error joined in `aria-describedby`; `aria-invalid` only when invalid; error `role=alert` |
| TimeField | native `input type=time` (step 60), tabular figures; `min-height` 44 px; the saved value is also shown beside the control in 24-hour text ("= 22:00") because a phone may display 12-hour time; From and Until sit in one row with a visible "until" between them and wrap at 320 px | Native: type digits, arrows change segments | Name from label ("From", "Until" inside the legend "Quiet hours"); value announced natively. Fallback if the browser lacks support: stepped select of 15-minute values (C-7); a stored value that is not on the 15-minute grid (for example 22:10 set through Telegram) is shown as it is and never rounded. |
| ZoneCombobox | ARIA 1.2 combobox with list-autocomplete: `role=combobox`, `aria-expanded`, `aria-controls`, `aria-autocomplete=list`, `aria-activedescendant`; listbox of options with place name and local time; same lookup and aliases as Telegram (ADR-0028); each option reads "Bangkok, Thailand, UTC+7, 03:42 now"; the hint says "Type a city or a country, for example Bangkok."; "UTC+7" and "GMT+7" are accepted if the lookup supports them (else the hint says so); the stored value stays visible as "Currently: Europe/Amsterdam"; live local time paragraph below | Type to filter; Down/Up move the active option (focus stays in input); Enter selects; Escape closes, a second Escape restores the saved value (the hint says so); Tab accepts nothing unselected; Home/End move in the input. A country with several zones lists its zones. | Active option announced through `aria-activedescendant`; result count announced in a visually hidden polite region ("3 places found"); the live local time sits in an `aria-live=polite` region updated only after typing pauses (300 ms) and on selection, wording "In Amsterdam it is 21:42 right now." Option text includes the time so it is not colour or position dependent. Unknown text gives a hint, not a red error: "Nothing found for 'Phuket'. Try the nearest bigger city, or the country." The field is never left empty on blur; the listbox stays visible above the on-screen keyboard. |
| Banner | kinds danger, success, info; title + text + optional action; border-left plus bold title so colour is not the only cue | Action is a normal button; focus moved to it only for blocking errors (403, conflict) | `role=alert` for danger and conflict, `role=status` for success/info; rendered once, not re-announced on every render |
| ConfirmDialog | `role=alertdialog` (or native `<dialog>` with `showModal`), title, description, two buttons; initial focus on the safe button "Keep my settings"; destructive button "Reset to defaults" | Focus trapped; Escape cancels; Tab cycles; focus returns to the Reset button on close; background inert | `aria-labelledby` title, `aria-describedby` description; no backdrop click needed to dismiss |
| LastChangeLine | text "Last changed from Telegram at 14:02" or "from the web"; `<time datetime>`; hidden when there is no audit record yet ("Using the default settings.") | not focusable | Plain text, read in order; updates after save are announced by the success banner, not by this line |

## Cross-cutting rules

- Targets: all controls 44 px on touch and never below 24 px at any size (WCAG 2.5.8); spacing between adjacent targets at least 8 px.
- Focus: visible ring on every interactive element in both themes; skip link to `main`; page title changes per screen ("Settings - Mail Assistant"); `lang="en"`.
- Errors: one `aria-live` region per page for status (saving, saved); field errors are `role=alert`; first invalid field focused on submit; multiple errors: the message names the field.
- Zoom and reflow: layout is fluid; no fixed heights; text may grow to 200 % without clipping.
- Motion: only `transform`/`opacity`, under 250 ms; `prefers-reduced-motion` removes it.
- Theme: follows system preference through tokens (semantic names in Tailwind, no loose `dark:` colours).
- Security display rules: values rendered as text only (AC-14); e-mail shown for identity, never used to decide access; refusals use human text, no codes.
- Test hooks: each component gets Vitest + axe (contrast off in jsdom); Playwright with axe at 375/768/1280 for contrast; token contrast test in `packages/tokens`.
