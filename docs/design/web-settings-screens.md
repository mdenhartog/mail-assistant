---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
status: approved
approver: Marco
date: 2026-11-10
---

# Web settings: screens, states and components

Direction: Pebble (ADR-0035): one soft card per setting (2 by 2 on desktop, stacked on a phone), pill buttons, one short greeting bubble at the top of the settings page that carries no control. Words per C-11 and AC-24. Sign-in is a username and an e-mailed code (ADR-0036). Mobile first; checked at 320, 375, 768, 1280 px and 200 % text size, no horizontal scroll (AC-22).

## Screen 1: Login page (`/login`, public, two steps)

Sign-in is a username, then a code sent by e-mail (ADR-0036). Both steps are on `/login`; step 2 replaces the content of step 1 without a new page load, and the page title stays "Sign in - Mail Assistant". `h1` first in `main` in both steps.

**Step 1: username.** Content: brand, heading "Sign in", a label "Username" with a text field (`autocomplete=username`, `autocapitalize=none`, `spellcheck=false`), one primary button "Send me a code", and a fine-print line: "We send a one-time code to the e-mail address on file for this username. This page never asks for access to your mail or calendar."

**Step 2: code.** Content: heading "Enter your code", the line "We sent a code to `m***@example.com`. It is valid for 10 minutes.", a label "Code" with a numeric field (`inputmode=numeric`, `autocomplete=one-time-code`, `pattern=[0-9]*`, `maxlength=6`, six digits, no spinner), a primary button "Sign in", a secondary button "Send a new code", and a link-styled button "Use another username". The e-mail says that the code is valid for 10 minutes and has no link, so the page does not mention a link.

"Send a new code" is disabled for 60 seconds after a code was sent, with visible text beside it: "You can ask for a new code in 52 seconds." The countdown text updates every second on screen but is not announced every second (see Accessibility). When it reaches zero the button is enabled and the text becomes "You can ask for a new code now." (announced once). A new code replaces the old one: the page says "A new code was sent. The earlier code no longer works."

| State | Behaviour |
| --- | --- |
| Default (step 1) | The username field is focused order first; the button is the only other control. |
| Sending | Button disabled, text "Sending...", `aria-busy` on the button, status "Sending your code." in a polite live region. Inputs `readonly`. |
| Code sent (step 2) | Step 2 appears, focus moves to the code field, status (polite, once): "Code sent to `m***@example.com`. It is valid for 10 minutes." The message is the same whether or not the username is known, so the page never says that a username exists or not. |
| Wrong code | Inline error in a `role=alert` element linked to the code field with `aria-describedby`, field `aria-invalid=true`, focus stays in the field and the field is selected: "That code is not right. You have 3 tries left." (the number is `attemptsLeft` from the server's generic refusal body, which carries it only while the login request cookie is valid; without it the page shows the same text without a number). Text plus "!" mark plus border, never colour alone. The same generic text is shown for any code failure the server answers with 400, so the page does not say why. |
| Expired code | Banner `role=alert`: "This code has expired. Send yourself a new one." with the button "Send a new code" focused. The code field is cleared. |
| Too many attempts | Banner `role=alert`: "Too many wrong tries. This code no longer works. Send a new code." The code field is disabled until a new code is sent. |
| Asked too soon (429, cooldown) | Info banner (`role=status`): "Please wait before asking for another code. You can try again in 41 seconds." The seconds come from `Retry-After`; the countdown text follows the same rule as above. |
| Too many codes this hour (429, hourly cap) | Banner `role=alert`: "You have asked for too many codes this hour. Try again in about 25 minutes." The button stays disabled until the time has passed. No code is sent. |
| No code arrives | A failed send gives the same answer as a successful one (ADR-0036), so the page cannot tell. Step 2 carries a permanent hint: "No code after a few minutes? Ask for a new one after the countdown, or check the mail setup." There is no "could not send" state. |
| Locked by the web lock | Banner `role=alert`: "Web sign-in is locked. You can lift the lock in Telegram." No further detail. |
| Session expired (came from a save) | Info banner (`role=status`): "Your session ended. Sign in again; what you typed is kept." After sign-in return to `/settings` with the draft restored (AC-12). |
| Already signed in | Redirect to `/settings`. |

Accessibility of the login page:

- After step 1 succeeds, focus moves to the code field; the heading and the masked address are read first because the field is described by that sentence (`aria-describedby`).
- Errors are `role=alert` and rendered with the page state, so they are announced once; the field is `aria-invalid` only when invalid. Focus returns to the code field after a wrong code and to "Send a new code" after an expired code.
- The countdown text is a visible element with `aria-live=off`; a separate visually hidden polite status announces only the start ("You can ask for a new code in 60 seconds.") and the end ("You can ask for a new code now."), never every second. Under reduced motion the countdown is text only.
- The code field accepts paste and the one-time-code autofill of the phone; `maxlength` does not block pasting a code with spaces (spaces are removed before sending).
- Targets are 44 px, the buttons wrap and stack at 320 px and at 200 % text, and nothing is clipped.

## Screen 2: Settings page (`/settings`, session needed)

Layout order: header (brand, Sign out as POST button), `h1` Settings, a quiet line "Signed in as `m***@example.com`" (the masked address from `/api/session`, also on phones), four fields in this order: **Time zone first**, then Quiet hours, Daily overview, Remind-me-later default; banner area, last-change line, actions. Save changes is primary; in R2 Reset to defaults is a separate secondary button kept apart from Save. At 320 px and at 200 % text the two buttons stack, Save first.

The time zone comes first because the three times are clock times in that zone. Under the times a permanent sentence says "Quiet hours, the overview and reminders follow this time zone." The Time zone hint reads "The times below are local times in this zone." After the zone is changed and before saving, a preview line shows what changes, for example "Quiet hours will now be 22:00 to 07:00 Bangkok time (16:00 to 01:00 Amsterdam time)." The clock times stay as they are; only the moment they mean moves.

Fields (words as Telegram): Quiet hours (From, Until), Daily overview, Remind-me-later default, Time zone. Each has a one-line hint linked by `aria-describedby`.

| State | Behaviour |
| --- | --- |
| Loading | Skeleton rows plus visible text "Loading your settings"; container `aria-busy=true`; skeleton animation removed under reduced motion. Save and Reset not rendered yet. |
| Loaded (clean) | Four values, last-change line "Last changed from Telegram at 14:02" (times via `Intl.DateTimeFormat`, in the saved zone; `<time datetime>`). Save disabled until something changed (optional; if enabled always, still validates). |
| Dirty | Save enabled. Leaving the page with unsaved edits asks the browser prompt only if cheap; draft kept in memory and in `sessionStorage` for the session-expiry return (no secrets). |
| Saving | Save and Reset disabled (`aria-disabled`), label "Saving..."; inputs `readonly`; status "Saving your settings." in a polite live region (AC-23). |
| Saved | Success banner (`role=status`) with what is true now: "Saved at 21:42. Quiet hours are 23:00 to 07:00 (Bangkok time). A message with an Undo button follows on Telegram within about N minutes." N is `noticeIntervalMinutes` from `GET /api/session`, the agent's real run interval. The last-change line becomes "Last changed from the web at 21:42". Focus stays on Save. If the audit trigger rolls the write back, the page says "Nothing was saved". |
| Validation error (AC-10) | Server or shared-validation message next to the field, text plus "!" mark plus red border (never colour alone), `aria-invalid=true`, `aria-describedby` hint + error, error element `role=alert`. On submit, focus moves to the first invalid field. Text matches Telegram, for example "The overview at 23:00 would fall inside quiet hours (22:00 to 07:00). Pick a time outside them, for example 18:00." Nothing stored. |
| Save failed (network or 5xx) | Danger banner `role=alert`: "Could not save. Nothing was changed. Check your connection and try again." with "Try again". Typed values stay. |
| Conflict (409, AC-11) | Info banner `role=alert`: "Settings changed in Telegram at 14:02 (Amsterdam time). I loaded the new values. Nothing is saved until you press Save again." The fields show the new values. Every field Marco had edited is marked with his own value and two buttons: "Use mine" and "Keep Telegram's" (for example "You typed 22:30, Telegram now has 23:00"). Nothing is lost silently and nothing is saved until he presses Save again. The last-change line updates. Focus moves to the banner. |
| Session expired (401 on save, AC-12) | R1: nothing is stored, Marco is sent to sign in and returns to `/settings` with the stored values. R2: the typed values are kept in memory and restored after sign-in, with the banner "Welcome back. Your unsaved changes are restored. Check them and save."; they are never saved automatically. |
| Access refused (403) | Full-page message: "This request was not allowed." with "Back to sign in". No settings data in the DOM. |
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
- Security display rules: values rendered as text only (AC-14); the masked address is shown for identity and never used to decide access; the page never shows or stores a one-time code beyond the field; refusals use human text, no codes.
- Test hooks: each component gets Vitest + axe (contrast off in jsdom); Playwright with axe at 375/768/1280 for contrast; token contrast test in `packages/tokens`.
